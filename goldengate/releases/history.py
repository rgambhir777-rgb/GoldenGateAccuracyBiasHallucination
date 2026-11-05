"""Release-over-release history used by trend charts (dashboard and HTML report)."""

from __future__ import annotations

from goldengate.releases import store

TREND_METRICS = ("accuracy", "hallucination_rate", "citation_precision", "citation_recall", "max_slice_gap",
                 "counterfactual_consistency", "retrieval_recall_at_k")


def release_history() -> list[dict[str, object]]:
    """One row per release (ordered by release date) with its latest run's headline metrics."""
    baseline = store.get_baseline()
    rows = []
    for release in store.list_releases():
        runs = store.list_runs(release.release_id)
        if not runs:
            continue
        summary = store.run_summary(runs[0])
        rows.append({
            "release_id": release.release_id, "version": release.version, "description": release.description,
            "model": release.model, "prompt_hash": release.prompt_hash, "system": release.system,
            "retriever_config": release.retriever_config, "released_at": release.released_at,
            "is_baseline": release.release_id == baseline, "latest_run_id": summary["run_id"],
            "golden_version": summary["golden_version"], "verdict": summary["verdict"],
            "judge_mode": summary["judge_mode"], "run_count": len(runs), "finished_at": summary["finished_at"],
            "metrics": {k: v for k, v in summary["metrics"].items() if k in TREND_METRICS},
        })
    return rows
