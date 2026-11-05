"""Run-level records persisted as JSON (one file per run)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from goldengate.core.models import ItemResult, MetricValue, RunMeta
from goldengate.fairness.slices import FairnessReport

GateStatus = Literal["PASS", "FAIL", "SKIP"]
Verdict = Literal["SHIP", "BLOCKED"]


class GateResult(BaseModel):
    id: str
    description: str
    metric: str | None
    metric_label: str
    kind: str
    threshold: float | None
    status: GateStatus
    current: float | None = None
    baseline: float | None = None
    delta: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    message: str
    failing_items: list[str] = Field(default_factory=list)


class GateReport(BaseModel):
    verdict: Verdict
    baseline_run_id: str | None
    gates: list[GateResult]
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def failed(self) -> list[GateResult]:
        return [g for g in self.gates if g.status == "FAIL"]


class RunRecord(BaseModel):
    """Everything about one evaluation run."""

    meta: RunMeta
    metrics: dict[str, MetricValue]
    fairness: FairnessReport
    items: list[ItemResult]
    gates: GateReport | None = None

    def item(self, item_id: str) -> ItemResult | None:
        return next((i for i in self.items if i.item_id == item_id), None)

    def metric(self, name: str) -> float | None:
        mv = self.metrics.get(name)
        return mv.value if mv else None
