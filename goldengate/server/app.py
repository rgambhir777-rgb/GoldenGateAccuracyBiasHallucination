"""FastAPI application: JSON API under /api plus the built React dashboard."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from goldengate import __version__, paths
from goldengate.config import SECRET_KEYS, load_settings, mask_secret, save_env_values
from goldengate.gates.config import FAIRNESS_METRICS, DEFAULT_GATES_YAML, GateConfig, load_gates, save_gates
from goldengate.golden import store as golden
from goldengate.metrics.aggregate import METRICS
from goldengate.releases import store
from goldengate.releases.compare import compare_runs
from goldengate.releases.history import release_history
from goldengate.releases.models import RunRecord
from goldengate.reports.render import EXTENSIONS, render
from goldengate.retrieval.corpus import cached_corpus, chunk_index
from goldengate.server.jobs import JobBusy, JobManager
from goldengate.systems.registry import available_systems

jobs = JobManager()


class RunRequest(BaseModel):
    system: str
    golden: str = "latest"
    judge: str | None = None
    release: str | None = None


class BaselineRequest(BaseModel):
    release: str


class SettingsRequest(BaseModel):
    values: dict[str, str | None]


def _run(run_id: str) -> RunRecord:
    try:
        return store.load_run(store.resolve_run(run_id))
    except store.RunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _judge_status() -> dict[str, Any]:
    s = load_settings()
    provider = s.llm_provider
    effective = "offline" if s.judge_mode == "offline" or provider is None else "llm"
    warning = None
    if provider is None:
        warning = ("No API key configured: the offline judge is used for every score. Add a key in Settings "
                   "to enable the LLM judge.")
    return {"mode": s.judge_mode, "effective": effective, "provider": provider, "judge_model": s.judge_model,
            "warning": warning}


def _run_payload(record: RunRecord) -> dict[str, Any]:
    return {
        "meta": record.meta.model_dump(mode="json"),
        "metrics": {k: v.model_dump() for k, v in record.metrics.items()},
        "gates": record.gates.model_dump() if record.gates else None,
        "fairness": record.fairness.model_dump(exclude={"groups"}),
        "summary": {
            "items": len(record.items), "failing": sum(1 for i in record.items if not i.correct),
            "critical_failing": sum(1 for i in record.items if i.critical and not i.correct),
        },
    }


def _item_summary(r) -> dict[str, Any]:
    return {
        "item_id": r.item_id, "question": r.question, "category": r.category, "difficulty": r.difficulty,
        "answerable": r.answerable, "critical": r.critical, "slices": r.slices,
        "counterfactual_group": r.counterfactual_group, "correct": r.correct, "hallucinated": r.hallucinated,
        "key_fact_coverage": r.key_fact_coverage, "n_claims": r.n_claims, "n_bad_claims": r.n_bad_claims,
        "n_citations": r.n_citations, "failure_reasons": r.failure_reasons, "judge": r.judgment.judge,
        "answer_preview": r.response.answer[:180],
    }


def metric_catalog() -> list[dict[str, Any]]:
    catalog = [{"name": m.name, "label": m.label, "higher_is_better": m.higher_is_better, "kind": m.kind,
                "group": m.group, "formula": m.formula} for m in METRICS]
    catalog += [{"name": n, "label": label, "higher_is_better": hib, "kind": "rate", "group": "fairness",
                 "formula": ""} for n, (label, hib) in FAIRNESS_METRICS.items()]
    return catalog


def create_app() -> FastAPI:
    app = FastAPI(title="GoldenGate", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json")

    # ------------------------------------------------------------------ status / overview

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        active = jobs.active()
        return {"version": __version__, "judge": _judge_status(), "baseline": store.get_baseline(),
                "has_data": store.has_data(), "golden_versions": golden.list_versions(),
                "active_job": active.model_dump() if active else None}

    @app.get("/api/overview")
    def overview() -> dict[str, Any]:
        history = release_history()
        config = load_gates()
        thresholds = {g.metric: {"threshold": g.threshold, "kind": g.kind} for g in config.gates
                      if g.metric and g.kind in ("min", "max") and g.enabled}
        latest = store.latest_run_id()
        current = _run_payload(store.load_run(latest)) if latest else None
        return {"current": current, "history": history, "thresholds": thresholds, "baseline": store.get_baseline(),
                "metrics": metric_catalog()}

    # ------------------------------------------------------------------ releases / runs

    @app.get("/api/releases")
    def releases() -> list[dict[str, Any]]:
        rows = release_history()
        for row in rows:
            row["runs"] = [store.run_summary(r) for r in store.list_runs(str(row["release_id"]))]
        return rows

    @app.get("/api/runs")
    def runs(release: str | None = None) -> list[dict[str, Any]]:
        return [store.run_summary(r) for r in store.list_runs(release)]

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: str) -> dict[str, Any]:
        return _run_payload(_run(run_id))

    @app.get("/api/runs/{run_id}/items")
    def run_items(run_id: str, category: str | None = None, slice: str | None = Query(None, alias="slice"),
                  status: str | None = None, q: str | None = None, critical: bool | None = None) -> dict[str, Any]:
        record = _run(run_id)
        items = record.items
        if category:
            items = [i for i in items if i.category == category]
        if slice:
            dim, _, value = slice.partition(":")
            items = [i for i in items if i.slices.get(dim) == value]
        if status == "pass":
            items = [i for i in items if i.correct]
        elif status == "fail":
            items = [i for i in items if not i.correct]
        elif status == "hallucinated":
            items = [i for i in items if i.hallucinated]
        if critical is not None:
            items = [i for i in items if i.critical == critical]
        if q:
            needle = q.lower()
            items = [i for i in items if needle in i.question.lower() or needle in i.item_id]
        facets = {
            "categories": sorted({i.category for i in record.items}),
            "slices": sorted({f"{k}:{v}" for i in record.items for k, v in i.slices.items()}),
        }
        return {"run_id": record.meta.run_id, "total": len(record.items), "count": len(items), "facets": facets,
                "items": [_item_summary(i) for i in items]}

    @app.get("/api/runs/{run_id}/items/{item_id}")
    def run_item(run_id: str, item_id: str) -> dict[str, Any]:
        record = _run(run_id)
        item = record.item(item_id)
        if item is None:
            raise HTTPException(status_code=404, detail=f"Item '{item_id}' not in run")
        index = chunk_index(cached_corpus())
        cited = list(dict.fromkeys(item.response.citations))
        citations = [{"chunk_id": c, "exists": c in index, "gold": c in item.gold_chunk_ids,
                      "text": index[c].text if c in index else None,
                      "supports": any(c in cl.supporting_chunk_ids for cl in item.judgment.claims)} for c in cited]
        gold = [{"chunk_id": c, "text": index[c].text if c in index else None} for c in item.gold_chunk_ids]
        return {"item": item.model_dump(mode="json"), "citations": citations, "gold_chunks": gold,
                "retrieved": [{**r.model_dump(), "gold": r.chunk_id in item.gold_chunk_ids}
                              for r in item.response.retrieved]}

    @app.get("/api/runs/{run_id}/fairness")
    def run_fairness(run_id: str) -> dict[str, Any]:
        return _run(run_id).fairness.model_dump()

    @app.get("/api/runs/{run_id}/report")
    def run_report(run_id: str, format: str = "html", baseline: str | None = "baseline") -> Response:
        record = _run(run_id)
        base = None
        if baseline and baseline != "none":
            try:
                base = store.load_run(store.resolve_run(baseline))
            except store.RunNotFound:
                base = None
        try:
            text = render(format, record, base)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        media = {"html": "text/html", "md": "text/markdown", "json": "application/json", "junit": "application/xml"}
        filename = f"{record.meta.run_id}.{EXTENSIONS[format]}"
        return Response(text, media_type=media[format] + "; charset=utf-8",
                        headers={"Content-Disposition": f'inline; filename="{filename}"'})

    @app.get("/api/compare")
    def compare(baseline: str = "baseline", current: str = "latest") -> dict[str, Any]:
        result = compare_runs(_run(baseline), _run(current), samples=load_settings().bootstrap_samples)
        return result.model_dump()

    @app.get("/api/systems")
    def systems() -> list[dict[str, object]]:
        return available_systems(load_settings())

    @app.post("/api/runs", status_code=202)
    def start_run(req: RunRequest) -> dict[str, Any]:
        from goldengate.releases.runner import run_suite

        def work(progress) -> str:
            return run_suite(req.system, golden_version=req.golden, judge_mode=req.judge, release_id=req.release,
                             progress=progress).meta.run_id

        try:
            job = jobs.start("run", f"{req.system} on golden {req.golden}", work)
        except JobBusy as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return job.model_dump()

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str) -> dict[str, Any]:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return job.model_dump()

    @app.post("/api/demo/reset", status_code=202)
    def reset_demo() -> dict[str, Any]:
        from goldengate.demo import seed_demo

        def work(progress) -> str | None:
            seed_demo(reset=True, on_step=lambda i, n, label: progress(i, n, label))
            return store.latest_run_id()

        try:
            job = jobs.start("demo", "Reset demo data", work)
        except JobBusy as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return job.model_dump()

    # ------------------------------------------------------------------ baseline

    @app.get("/api/baseline")
    def get_baseline() -> dict[str, Any]:
        release = store.get_baseline()
        return {"release": release, "run_id": store.latest_run_id(release) if release else None}

    @app.put("/api/baseline")
    def put_baseline(req: BaselineRequest) -> dict[str, Any]:
        try:
            store.set_baseline(req.release)
        except store.RunNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return get_baseline()

    # ------------------------------------------------------------------ golden

    @app.get("/api/golden")
    def golden_versions() -> list[dict[str, Any]]:
        out = []
        for v in golden.list_versions():
            manifest = golden.load_manifest(v).model_dump()
            check = golden.validate(v)
            out.append({**manifest, "valid": check.ok, "errors": check.errors, "warnings": check.warnings})
        return out

    @app.get("/api/golden/diff")
    def golden_diff(a: str, b: str) -> dict[str, Any]:
        try:
            d = golden.diff(golden.resolve_version(a), golden.resolve_version(b))
        except golden.GoldenError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"a": d.a, "b": d.b, "added": d.added, "removed": d.removed, "changed": d.changed,
                "details": d.details, "unchanged": d.unchanged}

    @app.get("/api/golden/{version}/items")
    def golden_items(version: str, q: str | None = None, category: str | None = None,
                     kind: str | None = None) -> dict[str, Any]:
        try:
            items = golden.load_items(golden.resolve_version(version))
        except golden.GoldenError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if category:
            items = [i for i in items if i.category == category]
        if kind == "counterfactual":
            items = [i for i in items if i.counterfactual_group]
        elif kind == "unanswerable":
            items = [i for i in items if not i.answerable]
        elif kind == "factual":
            items = [i for i in items if i.answerable and not i.counterfactual_group]
        if q:
            items = [i for i in items if q.lower() in i.question.lower() or q.lower() in i.id]
        return {"version": version, "count": len(items), "items": [i.model_dump() for i in items]}

    # ------------------------------------------------------------------ gates

    @app.get("/api/gates")
    def get_gates() -> dict[str, Any]:
        config = load_gates()
        return {"config": config.model_dump(), "metrics": metric_catalog(), "default_yaml": DEFAULT_GATES_YAML}

    @app.put("/api/gates")
    def put_gates(config: dict[str, Any]) -> dict[str, Any]:
        try:
            parsed = GateConfig.model_validate(config)
        except ValidationError as exc:
            messages = [e["msg"].removeprefix("Value error, ") for e in exc.errors()]
            raise HTTPException(status_code=422, detail="; ".join(messages)) from exc
        save_gates(parsed)
        return {"config": parsed.model_dump(), "saved": True}

    # ------------------------------------------------------------------ settings

    @app.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        s = load_settings()
        return {
            "keys": {"ANTHROPIC_API_KEY": mask_secret(s.anthropic_api_key), "OPENAI_API_KEY": mask_secret(s.openai_api_key)},
            "values": {"GOLDENGATE_JUDGE_MODE": s.judge_mode, "GOLDENGATE_JUDGE_MODEL": s.judge_model,
                       "GOLDENGATE_RAG_MODEL": s.rag_model, "GOLDENGATE_OPENAI_MODEL": s.openai_model,
                       "OPENAI_BASE_URL": s.openai_base_url, "GOLDENGATE_RETRIEVER": s.retriever,
                       "GOLDENGATE_TOP_K": str(s.top_k), "GOLDENGATE_BOOTSTRAP_SAMPLES": str(s.bootstrap_samples)},
            "judge": _judge_status(), "env_file": str(paths.env_file()),
        }

    @app.put("/api/settings")
    def put_settings(req: SettingsRequest) -> dict[str, Any]:
        values = dict(req.values)
        for key in SECRET_KEYS:
            if key in values and values[key] and values[key].startswith("*"):
                values.pop(key)  # masked placeholder sent back unchanged
        choices = {"GOLDENGATE_JUDGE_MODE": ("auto", "offline", "llm"), "GOLDENGATE_RETRIEVER": ("bm25", "tfidf")}
        for key, allowed in choices.items():
            if values.get(key) and values[key] not in allowed:
                raise HTTPException(status_code=422, detail=f"{key} must be one of {', '.join(allowed)}")
        for key, (lo, hi) in {"GOLDENGATE_TOP_K": (1, 20), "GOLDENGATE_BOOTSTRAP_SAMPLES": (100, 20000)}.items():
            if values.get(key):
                try:
                    number = int(str(values[key]))
                except ValueError:
                    raise HTTPException(status_code=422, detail=f"{key} must be an integer") from None
                if not lo <= number <= hi:
                    raise HTTPException(status_code=422, detail=f"{key} must be between {lo} and {hi}")
        try:
            save_env_values(values)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return get_settings()

    # ------------------------------------------------------------------ frontend

    dist = paths.frontend_dist()
    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> Response:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = dist / full_path
        if full_path and candidate.is_file() and dist in candidate.resolve().parents:
            return FileResponse(candidate)
        index = dist / "index.html"
        if index.exists():
            return FileResponse(index)
        return HTMLResponse("<h1>GoldenGate API is running</h1><p>The dashboard build (frontend/dist) is missing. "
                            "Run <code>npm install && npm run build</code> in <code>frontend/</code>.</p>"
                            "<p>API docs: <a href='/api/docs'>/api/docs</a></p>")

    @app.exception_handler(golden.GoldenError)
    def golden_error(_, exc: golden.GoldenError) -> PlainTextResponse:
        return PlainTextResponse(str(exc), status_code=400)

    return app
