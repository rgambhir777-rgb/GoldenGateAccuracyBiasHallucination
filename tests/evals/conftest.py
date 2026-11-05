"""Release gates as pytest tests.

Select what to evaluate with environment variables:

* ``GOLDENGATE_RUN`` - run ID, release ID or ``latest`` (default ``latest``)
* ``GOLDENGATE_BASELINE`` - run ID, release ID or ``baseline`` (default ``baseline``)

If the workspace has no runs yet, the demo data is seeded first so the suite
always has something to evaluate.
"""

from __future__ import annotations

import os

import pytest

from goldengate.gates.config import load_gates
from goldengate.gates.engine import evaluate_gates
from goldengate.releases import store
from goldengate.releases.models import GateReport, RunRecord


def _load() -> tuple[RunRecord, RunRecord | None, GateReport]:
    if not store.has_data():
        from goldengate.demo import seed_demo

        seed_demo()
    current = store.load_run(store.resolve_run(os.environ.get("GOLDENGATE_RUN", "latest")))
    try:
        baseline = store.load_run(store.resolve_run(os.environ.get("GOLDENGATE_BASELINE", "baseline")))
    except store.RunNotFound:
        baseline = None
    return current, baseline, evaluate_gates(load_gates(), current, baseline)


_STATE: tuple[RunRecord, RunRecord | None, GateReport] | None = None


def state() -> tuple[RunRecord, RunRecord | None, GateReport]:
    global _STATE
    if _STATE is None:
        _STATE = _load()
    return _STATE


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    current, _, report = state()
    if "gate_result" in metafunc.fixturenames:
        metafunc.parametrize("gate_result", report.gates, ids=[g.id for g in report.gates])
    if "critical_item" in metafunc.fixturenames:
        items = [i for i in current.items if i.critical]
        metafunc.parametrize("critical_item", items, ids=[i.item_id for i in items])


def pytest_report_header(config: pytest.Config) -> list[str]:
    current, baseline, report = state()
    return [
        f"goldengate run: {current.meta.run_id} (release {current.meta.release.release_id}, "
        f"golden {current.meta.golden_version})",
        f"goldengate baseline: {baseline.meta.run_id if baseline else 'none'}",
        f"goldengate verdict: {report.verdict}",
    ]
