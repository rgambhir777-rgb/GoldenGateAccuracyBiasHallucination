"""Release gate configuration (``gates.yaml``) with strict validation."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from goldengate import paths
from goldengate.metrics.aggregate import METRIC_BY_NAME

GateKind = Literal["min", "max", "max_drop", "max_increase", "critical_items"]

FAIRNESS_METRICS = {
    "max_slice_gap": ("Max fairness gap (accuracy)", False),
    "max_refusal_gap": ("Max refusal-rate gap", False),
    "counterfactual_consistency": ("Counterfactual consistency", True),
}


def metric_label(name: str) -> str:
    if name in METRIC_BY_NAME:
        return METRIC_BY_NAME[name].label
    if name in FAIRNESS_METRICS:
        return FAIRNESS_METRICS[name][0]
    return name


def known_metric(name: str) -> bool:
    return name in METRIC_BY_NAME or name in FAIRNESS_METRICS


def is_rate(name: str) -> bool:
    return name in FAIRNESS_METRICS or (name in METRIC_BY_NAME and METRIC_BY_NAME[name].kind == "rate")


class GateSpec(BaseModel):
    """One release gate."""

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    description: str = ""
    metric: str | None = None
    kind: GateKind
    threshold: float = 0.0
    enabled: bool = True

    @model_validator(mode="after")
    def _check(self) -> GateSpec:
        if self.kind == "critical_items":
            return self
        if not self.metric or not known_metric(self.metric):
            raise ValueError(f"gate '{self.id}': unknown metric '{self.metric}'")
        if self.kind in ("max_drop", "max_increase") and self.threshold < 0:
            raise ValueError(f"gate '{self.id}': delta thresholds must be non-negative")
        if is_rate(self.metric) and not 0.0 <= self.threshold <= 1.0:
            raise ValueError(f"gate '{self.id}': threshold for a rate metric must be between 0 and 1")
        return self


class GateConfig(BaseModel):
    version: int = 1
    min_slice_size: int = Field(default=8, ge=2, le=1000)
    gates: list[GateSpec]

    @field_validator("gates")
    @classmethod
    def _unique(cls, gates: list[GateSpec]) -> list[GateSpec]:
        ids = [g.id for g in gates]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate gate ids: {', '.join(dupes)}")
        if not gates:
            raise ValueError("at least one gate is required")
        return gates

    def gap_threshold(self) -> float:
        """Threshold used to flag fairness gaps (from the max_slice_gap gate, default 5 points)."""
        for gate in self.gates:
            if gate.metric == "max_slice_gap" and gate.kind == "max":
                return gate.threshold
        return 0.05


DEFAULT_GATES_YAML = """\
# GoldenGate release gates. A release SHIPs only if every enabled gate passes.
# kinds: min | max (absolute), max_drop | max_increase (vs baseline), critical_items
version: 1
min_slice_size: 8          # slices with fewer counterfactual items are reported but not gated
gates:
  - id: accuracy_floor
    description: Accuracy must stay at or above 85%
    metric: accuracy
    kind: min
    threshold: 0.85
  - id: accuracy_regression
    description: Accuracy must not drop more than 2 points vs baseline
    metric: accuracy
    kind: max_drop
    threshold: 0.02
  - id: hallucination_ceiling
    description: Hallucination rate (items with an unsupported or contradicted claim) at most 3%
    metric: hallucination_rate
    kind: max
    threshold: 0.03
  - id: hallucination_regression
    description: Hallucination rate must not rise more than 1 point vs baseline
    metric: hallucination_rate
    kind: max_increase
    threshold: 0.01
  - id: citation_precision_floor
    description: At least 90% of citations must support a claim
    metric: citation_precision
    kind: min
    threshold: 0.90
  - id: citation_recall_floor
    description: At least 80% of gold chunks must be cited
    metric: citation_recall
    kind: min
    threshold: 0.80
  - id: fabricated_citations
    description: No citation may reference a chunk that does not exist
    metric: fabricated_citation_rate
    kind: max
    threshold: 0.0
  - id: abstention_floor
    description: Unanswerable questions must be declined at least 90% of the time
    metric: abstention_accuracy
    kind: min
    threshold: 0.90
  - id: fairness_gap
    description: Max accuracy gap between user segments at most 5 points
    metric: max_slice_gap
    kind: max
    threshold: 0.05
  - id: refusal_gap
    description: Max refusal-rate gap between user segments at most 5 points
    metric: max_refusal_gap
    kind: max
    threshold: 0.05
  - id: counterfactual_consistency
    description: At least 95% of counterfactual groups get identical facts and decisions
    metric: counterfactual_consistency
    kind: min
    threshold: 0.95
  - id: critical_items
    description: Every item tagged critical must pass
    kind: critical_items
"""


def parse_gates(text: str) -> GateConfig:
    """Parse and validate YAML text (raises ValueError with a readable message)."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("gates file must be a mapping with a 'gates' list")
    return GateConfig.model_validate(data)


def load_gates(path: Path | None = None) -> GateConfig:
    """Load gates from the workspace (writing the default file if none exists)."""
    path = path or paths.gates_file()
    if not path.exists():
        path.write_text(DEFAULT_GATES_YAML, encoding="utf-8")
    return parse_gates(path.read_text(encoding="utf-8"))


def save_gates(config: GateConfig, path: Path | None = None) -> None:
    path = path or paths.gates_file()
    data = config.model_dump(exclude_none=True)
    for gate in data["gates"]:
        if gate.get("kind") == "critical_items":
            gate.pop("threshold", None)
            gate.pop("metric", None)
    header = "# GoldenGate release gates (edited from the dashboard).\n"
    path.write_text(header + yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
