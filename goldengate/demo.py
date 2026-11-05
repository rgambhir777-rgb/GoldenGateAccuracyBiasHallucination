"""Seed the workspace with the four demo releases so the dashboard tells a story immediately."""

from __future__ import annotations

from collections.abc import Callable

from goldengate.gates.config import load_gates
from goldengate.gates.engine import evaluate_gates
from goldengate.releases import store
from goldengate.releases.runner import run_suite

DEMO_PLAN: tuple[tuple[str, str], ...] = (
    ("release_1.0", "v1"),  # historical run on the first golden version
    ("release_1.0", "v2"),  # re-baselined on golden v2
    ("release_1.1", "v2"),
    ("release_1.2", "v2"),
    ("release_1.3", "v2"),
)
BASELINE = "release_1.0"

StepCallback = Callable[[int, int, str], None]


def regate(run_id: str) -> None:
    """Recompute and persist a run's gate verdict against the current baseline."""
    record = store.load_run(run_id)
    record.gates = evaluate_gates(load_gates(), record, store.baseline_run())
    store.save_run(record)


def seed_demo(reset: bool = False, on_step: StepCallback | None = None) -> list[str]:
    """Run every demo release with the offline judge and set ``release_1.0`` as baseline.

    The offline judge is always used here so the demo is deterministic and free;
    LLM-judged runs can be started separately from the CLI or dashboard.
    Returns the run IDs created.
    """
    if reset:
        store.delete_all()
    run_ids: list[str] = []
    for step, (release, version) in enumerate(DEMO_PLAN, start=1):
        if on_step:
            on_step(step, len(DEMO_PLAN), f"{release} on golden {version}")
        record = run_suite(release, golden_version=version, judge_mode="offline")
        run_ids.append(record.meta.run_id)
        if release == BASELINE and version == "v2":
            store.set_baseline(BASELINE)
            regate(record.meta.run_id)
    return run_ids


def ensure_demo_data(on_step: StepCallback | None = None) -> bool:
    """Seed only when the workspace has no runs. Returns True if seeding happened."""
    if store.has_data():
        return False
    seed_demo(on_step=on_step)
    return True
