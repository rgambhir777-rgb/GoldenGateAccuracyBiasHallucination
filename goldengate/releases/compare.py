"""Compare a run against a baseline run: metric deltas with paired CIs, item and slice changes."""

from __future__ import annotations

from pydantic import BaseModel, Field

from goldengate.gates.config import FAIRNESS_METRICS, load_gates
from goldengate.gates.engine import evaluate_gates
from goldengate.metrics.aggregate import METRIC_BY_NAME, METRICS
from goldengate.metrics.bootstrap import paired_ratio_delta_ci
from goldengate.releases.models import GateReport, RunRecord


class MetricDelta(BaseModel):
    name: str
    label: str
    group: str
    kind: str
    higher_is_better: bool
    baseline: float | None
    current: float | None
    delta: float | None
    delta_ci_low: float | None = None
    delta_ci_high: float | None = None
    significant: bool = False
    regression: bool = False


class ItemChange(BaseModel):
    item_id: str
    question: str
    category: str
    critical: bool
    slices: dict[str, str] = Field(default_factory=dict)
    baseline_correct: bool
    current_correct: bool
    reasons: list[str] = Field(default_factory=list)
    baseline_answer: str = ""
    current_answer: str = ""


class SliceChange(BaseModel):
    dimension: str
    value: str
    metric: str
    baseline: float
    current: float
    delta: float


class Comparison(BaseModel):
    baseline_run_id: str
    current_run_id: str
    baseline_release: str
    current_release: str
    baseline_golden: str
    current_golden: str
    common_items: int
    warnings: list[str] = Field(default_factory=list)
    metrics: list[MetricDelta]
    newly_failing: list[ItemChange]
    newly_passing: list[ItemChange]
    slice_changes: list[SliceChange]
    gates: GateReport


def compare_runs(baseline: RunRecord, current: RunRecord, samples: int = 1000, seed: int = 7) -> Comparison:
    """Metric deltas (paired bootstrap on shared items), newly failing items first, slice deltas."""
    warnings: list[str] = []
    if baseline.meta.golden_version != current.meta.golden_version:
        warnings.append(
            f"Golden versions differ ({baseline.meta.golden_version} vs {current.meta.golden_version}); "
            "item-level comparisons use only the items present in both runs."
        )
    base_items = {r.item_id: r for r in baseline.items}
    cur_items = {r.item_id: r for r in current.items}
    common = [i for i in cur_items if i in base_items]

    deltas: list[MetricDelta] = []
    for spec in METRICS:
        b_val, c_val = baseline.metric(spec.name), current.metric(spec.name)
        rows = [(spec.extract(base_items[i]), spec.extract(cur_items[i])) for i in common]
        rows = [(b, c) for b, c in rows if b is not None and c is not None]
        low = high = None
        if rows:
            _, low, high = paired_ratio_delta_ci([b[0] for b, _ in rows], [b[1] for b, _ in rows],
                                                 [c[0] for _, c in rows], [c[1] for _, c in rows], samples, seed)
        delta = None if b_val is None or c_val is None else round(c_val - b_val, 4)
        significant = low is not None and high is not None and (low > 0 or high < 0)
        worse = delta is not None and ((delta < 0) if spec.higher_is_better else (delta > 0))
        deltas.append(MetricDelta(
            name=spec.name, label=spec.label, group=spec.group, kind=spec.kind,
            higher_is_better=spec.higher_is_better, baseline=b_val, current=c_val, delta=delta,
            delta_ci_low=None if low is None else round(low, 4), delta_ci_high=None if high is None else round(high, 4),
            significant=significant, regression=worse and significant,
        ))
    for name, (label, higher) in FAIRNESS_METRICS.items():
        b_val, c_val = baseline.metric(name), current.metric(name)
        delta = None if b_val is None or c_val is None else round(c_val - b_val, 4)
        worse = delta is not None and ((delta < 0) if higher else (delta > 0))
        deltas.append(MetricDelta(name=name, label=label, group="fairness", kind="rate", higher_is_better=higher,
                                  baseline=b_val, current=c_val, delta=delta, regression=worse and abs(delta) > 0.02))

    def change(item_id: str) -> ItemChange:
        b, c = base_items[item_id], cur_items[item_id]
        return ItemChange(item_id=item_id, question=c.question, category=c.category, critical=c.critical,
                          slices=c.slices, baseline_correct=b.correct, current_correct=c.correct,
                          reasons=c.failure_reasons, baseline_answer=b.response.answer, current_answer=c.response.answer)

    newly_failing = sorted((change(i) for i in common if base_items[i].correct and not cur_items[i].correct),
                           key=lambda x: (not x.critical, x.item_id))
    newly_passing = [change(i) for i in common if not base_items[i].correct and cur_items[i].correct]

    base_slices = {(s.dimension, s.value): s for s in baseline.fairness.slices}
    slice_changes = []
    for s in current.fairness.slices:
        b = base_slices.get((s.dimension, s.value))
        if not b:
            continue
        for metric in ("accuracy", "refusal_rate", "helpfulness"):
            slice_changes.append(SliceChange(dimension=s.dimension, value=s.value, metric=metric,
                                             baseline=b.metrics[metric], current=s.metrics[metric],
                                             delta=round(s.metrics[metric] - b.metrics[metric], 4)))
    slice_changes.sort(key=lambda x: -abs(x.delta))

    gates = evaluate_gates(load_gates(), current, baseline)
    return Comparison(
        baseline_run_id=baseline.meta.run_id, current_run_id=current.meta.run_id,
        baseline_release=baseline.meta.release.release_id, current_release=current.meta.release.release_id,
        baseline_golden=baseline.meta.golden_version, current_golden=current.meta.golden_version,
        common_items=len(common), warnings=warnings, metrics=deltas,
        newly_failing=newly_failing, newly_passing=newly_passing, slice_changes=slice_changes, gates=gates,
    )


def headline_metric_names() -> list[str]:
    """Metrics shown in PR comments and the compare page header, in order."""
    names = ["accuracy", "key_fact_coverage", "abstention_accuracy", "hallucination_rate",
             "claim_hallucination_rate", "citation_precision", "citation_recall", "fabricated_citation_rate",
             "retrieval_recall_at_k", "mrr"]
    return [n for n in names if n in METRIC_BY_NAME] + list(FAIRNESS_METRICS)
