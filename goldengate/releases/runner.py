"""Run a system over a golden version, judge, score, gate and persist the result."""

from __future__ import annotations

import os
import subprocess
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone

from goldengate import paths
from goldengate.config import Settings, load_settings
from goldengate.core.models import MetricValue, Response, RunMeta
from goldengate.fairness.slices import fairness_report
from goldengate.gates.config import load_gates
from goldengate.gates.engine import evaluate_gates
from goldengate.golden import store as golden
from goldengate.judges.factory import build_judge
from goldengate.judges.llm import LLMJudge
from goldengate.metrics.aggregate import compute_metrics
from goldengate.metrics.scoring import score_item
from goldengate.releases import store
from goldengate.releases.models import RunRecord
from goldengate.retrieval.corpus import cached_corpus, chunk_index
from goldengate.systems.base import stable_hash
from goldengate.systems.registry import build_system

Progress = Callable[[int, int, str], None]


def git_commit() -> str:
    """Commit of the code under test (GITHUB_SHA in CI, else ``git rev-parse``)."""
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"][:12]
    try:
        out = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=paths.resource_root(),
                             capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else "unknown"


def fairness_metrics(record_fairness) -> dict[str, MetricValue]:
    """Expose headline fairness numbers as metrics so gates and trends can use them."""
    f = record_fairness
    n_cf = sum(s.n for s in f.slices)
    return {
        "max_slice_gap": MetricValue(name="max_slice_gap", value=f.max_accuracy_gap,
                                     ci_low=f.max_accuracy_gap_ci[0] if f.max_accuracy_gap_ci else None,
                                     ci_high=f.max_accuracy_gap_ci[1] if f.max_accuracy_gap_ci else None, n=n_cf),
        "max_refusal_gap": MetricValue(name="max_refusal_gap", value=f.max_refusal_gap, n=n_cf),
        "counterfactual_consistency": MetricValue(
            name="counterfactual_consistency", value=f.counterfactual_consistency,
            ci_low=f.counterfactual_consistency_ci[0] if f.counterfactual_consistency_ci else None,
            ci_high=f.counterfactual_consistency_ci[1] if f.counterfactual_consistency_ci else None,
            n=len(f.groups)),
    }


def run_suite(system_spec: str, golden_version: str | None = None, judge_mode: str | None = None,
              release_id: str | None = None, settings: Settings | None = None,
              progress: Progress | None = None) -> RunRecord:
    """Evaluate one release end to end and persist the run.

    Raises :class:`goldengate.golden.store.GoldenError` if the golden set fails
    validation (for example a frozen version was edited).
    """
    settings = settings or load_settings()
    mode = judge_mode or settings.judge_mode
    version = golden.resolve_version(golden_version)
    validation = golden.validate(version)
    if not validation.ok:
        raise golden.GoldenError("; ".join(validation.errors))
    items = golden.load_items(version)
    chunks = chunk_index(cached_corpus())
    system = build_system(system_spec, settings, items=items, release_id=release_id)
    judge, warnings = build_judge(mode, settings, chunks)
    started = datetime.now(timezone.utc)

    results = []
    for n, item in enumerate(items, start=1):
        try:
            response = system.answer(item.question, item.user_context)
        except Exception as exc:  # noqa: BLE001 - one bad item must not abort the run
            response = Response(answer="", error=f"{exc.__class__.__name__}: {exc}")
        judgment = judge.judge(item, response)
        results.append(score_item(item, response, judgment, chunks, k=settings.top_k))
        if progress:
            progress(n, len(items), item.id)

    if isinstance(judge, LLMJudge):
        if judge.fallbacks:
            warnings.append(f"LLM judge fell back to the offline judge for {judge.fallbacks} item(s)"
                            + (f": {judge.disabled_reason}" if judge.disabled_reason else ""))

    gates_cfg = load_gates()
    metrics = compute_metrics(results, samples=settings.bootstrap_samples, seed=settings.seed)
    fairness = fairness_report(results, min_slice_size=gates_cfg.min_slice_size,
                               gap_threshold=gates_cfg.gap_threshold(), samples=settings.bootstrap_samples,
                               seed=settings.seed)
    metrics.update(fairness_metrics(fairness))

    info = system.release_info()
    finished = datetime.now(timezone.utc)
    run_id = f"{info.release_id}-{finished:%Y%m%d-%H%M%S}-{stable_hash(finished.isoformat(), length=4)}"
    meta = RunMeta(
        run_id=run_id, release=info, golden_version=version, golden_hash=golden.content_hash(version),
        git_commit=git_commit(), judge_mode=mode,
        judges_used=dict(Counter(r.judgment.judge for r in results)), started_at=started, finished_at=finished,
        n_items=len(results), warnings=warnings,
    )
    record = RunRecord(meta=meta, metrics=metrics, fairness=fairness, items=results)
    record.gates = evaluate_gates(gates_cfg, record, store.baseline_run())
    store.save_run(record)
    return record
