"""One test per release gate and one per critical golden item."""

from __future__ import annotations

import pytest

from goldengate.core.models import ItemResult
from goldengate.releases.models import GateResult


def _num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def test_gate(gate_result: GateResult) -> None:
    if gate_result.status == "SKIP":
        pytest.skip(gate_result.message)
    assert gate_result.status == "PASS", (
        f"Gate '{gate_result.id}' FAILED: {gate_result.message}\n"
        f"  metric    : {gate_result.metric_label} ({gate_result.metric})\n"
        f"  baseline  : {_num(gate_result.baseline)}\n"
        f"  current   : {_num(gate_result.current)}\n"
        f"  delta     : {_num(gate_result.delta)}\n"
        f"  threshold : {_num(gate_result.threshold)} ({gate_result.kind})"
        + (f"\n  failing   : {', '.join(gate_result.failing_items)}" if gate_result.failing_items else "")
    )


def test_critical_item(critical_item: ItemResult) -> None:
    assert critical_item.correct, (
        f"Critical item '{critical_item.item_id}' failed: {'; '.join(critical_item.failure_reasons)}\n"
        f"  question  : {critical_item.question}\n"
        f"  expected  : {critical_item.reference_answer}\n"
        f"  answer    : {critical_item.response.answer}"
    )
