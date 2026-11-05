"""Persist and query runs, releases and the baseline."""

from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy import delete, select

from goldengate import paths
from goldengate.core.models import ReleaseInfo
from goldengate.releases import db
from goldengate.releases.models import RunRecord

BASELINE_KEY = "baseline_release"


class RunNotFound(LookupError):
    """Raised when a run reference cannot be resolved."""


def _run_file(run_id: str) -> Path:
    return paths.runs_dir() / f"{run_id}.json"


def upsert_release(info: ReleaseInfo) -> None:
    with db.session() as s:
        row = s.get(db.ReleaseRow, info.release_id) or db.ReleaseRow(release_id=info.release_id)
        row.version, row.description, row.system = info.version, info.description, info.system
        row.model, row.prompt_hash, row.retriever_config = info.model, info.prompt_hash, info.retriever_config
        row.released_at = info.released_at
        s.add(row)
        s.commit()


def save_run(record: RunRecord) -> Path:
    """Write the run JSON file and index it (release, run, metrics) in SQLite."""
    meta = record.meta
    path = _run_file(meta.run_id)
    path.write_text(record.model_dump_json(indent=1), encoding="utf-8")
    upsert_release(meta.release)
    with db.session() as s:
        existing = s.get(db.RunRow, meta.run_id)
        if existing:
            s.delete(existing)
            s.flush()
        run = db.RunRow(
            run_id=meta.run_id, release_id=meta.release.release_id, golden_version=meta.golden_version,
            golden_hash=meta.golden_hash, git_commit=meta.git_commit, judge_mode=meta.judge_mode,
            judges_used=meta.judges_used, started_at=meta.started_at, finished_at=meta.finished_at,
            n_items=meta.n_items, verdict=record.gates.verdict if record.gates else None, result_path=str(path),
        )
        run.metrics = [db.MetricRow(name=m.name, value=m.value, ci_low=m.ci_low, ci_high=m.ci_high, n=m.n)
                       for m in record.metrics.values()]
        s.add(run)
        s.commit()
    return path


def load_run(run_id: str) -> RunRecord:
    path = _run_file(run_id)
    if not path.exists():
        raise RunNotFound(f"Run '{run_id}' not found")
    return RunRecord.model_validate_json(path.read_text(encoding="utf-8"))


def list_runs(release_id: str | None = None) -> list[db.RunRow]:
    """Runs newest first, optionally for one release."""
    with db.session() as s:
        query = select(db.RunRow).order_by(db.RunRow.started_at.desc())
        if release_id:
            query = query.where(db.RunRow.release_id == release_id)
        return list(s.scalars(query).all())


def list_releases() -> list[db.ReleaseRow]:
    """Releases ordered by release date (then creation)."""
    with db.session() as s:
        rows = list(s.scalars(select(db.ReleaseRow)).all())
    return sorted(rows, key=lambda r: (r.released_at or "9999", r.created_at))


def latest_run_id(release_id: str | None = None) -> str | None:
    runs = list_runs(release_id)
    return runs[0].run_id if runs else None


def resolve_run(ref: str | None) -> str:
    """Resolve ``latest``, a release ID (its latest run), ``baseline`` or a run ID."""
    if ref in (None, "", "latest"):
        run_id = latest_run_id()
        if not run_id:
            raise RunNotFound("No runs yet. Run 'goldengate demo' or 'goldengate run' first.")
        return run_id
    if ref == "baseline":
        release = get_baseline()
        if not release:
            raise RunNotFound("No baseline set. Run 'goldengate baseline set --release <id>'.")
        ref = release
    if _run_file(ref).exists():
        return ref
    run_id = latest_run_id(ref)
    if run_id:
        return run_id
    raise RunNotFound(f"No run or release named '{ref}'")


def get_baseline() -> str | None:
    with db.session() as s:
        row = s.get(db.SettingRow, BASELINE_KEY)
        return row.value if row else None


def set_baseline(release_id: str) -> str:
    """Mark a release as the baseline; it must have at least one run."""
    if not latest_run_id(release_id):
        raise RunNotFound(f"Release '{release_id}' has no runs; run it before making it the baseline")
    with db.session() as s:
        s.merge(db.SettingRow(key=BASELINE_KEY, value=release_id))
        s.commit()
    return release_id


def baseline_run() -> RunRecord | None:
    release = get_baseline()
    if not release:
        return None
    run_id = latest_run_id(release)
    return load_run(run_id) if run_id else None


def export_run(run_id: str, target: Path) -> Path:
    """Copy a run JSON file (used to commit the CI baseline)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_run_file(run_id), target)
    return target


def import_run(source: Path, as_baseline: bool = True) -> RunRecord:
    """Load a run JSON produced elsewhere (e.g. the committed CI baseline) into this workspace."""
    record = RunRecord.model_validate_json(source.read_text(encoding="utf-8"))
    save_run(record)
    if as_baseline:
        set_baseline(record.meta.release.release_id)
    return record


def delete_all() -> None:
    """Remove every run, release, metric and setting (keeps the judge cache)."""
    with db.session() as s:
        for table in (db.MetricRow, db.RunRow, db.ReleaseRow, db.SettingRow):
            s.execute(delete(table))
        s.commit()
    for file in paths.runs_dir().glob("*.json"):
        file.unlink()


def has_data() -> bool:
    return latest_run_id() is not None


def run_summary(row: db.RunRow) -> dict[str, object]:
    """Compact JSON-friendly summary of a run row."""
    with db.session() as s:
        metrics = {m.name: m.value for m in s.scalars(select(db.MetricRow).where(db.MetricRow.run_id == row.run_id))}
    return {
        "run_id": row.run_id, "release_id": row.release_id, "golden_version": row.golden_version,
        "judge_mode": row.judge_mode, "judges_used": row.judges_used, "started_at": row.started_at.isoformat(),
        "finished_at": row.finished_at.isoformat() if row.finished_at else None, "n_items": row.n_items,
        "verdict": row.verdict, "git_commit": row.git_commit, "metrics": metrics,
    }
