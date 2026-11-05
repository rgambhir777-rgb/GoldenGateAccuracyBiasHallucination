"""Evaluate release gates for a run against an optional baseline run."""

from __future__ import annotations

from goldengate.gates.config import GateConfig, GateSpec, metric_label
from goldengate.releases.models import GateReport, GateResult, RunRecord


def _fmt(value: float | None, metric: str | None) -> str:
    if value is None:
        return "n/a"
    if metric in ("avg_answer_words", "avg_latency_ms", "avg_total_tokens"):
        return f"{value:.1f}"
    return f"{value * 100:.1f}%"


def _pts(delta: float) -> str:
    return f"{delta * 100:+.1f} pts"


def evaluate_gate(gate: GateSpec, current: RunRecord, baseline: RunRecord | None) -> GateResult:
    """Evaluate a single gate; delta gates are skipped when no baseline exists."""
    label = metric_label(gate.metric) if gate.metric else "Critical items"
    base = dict(id=gate.id, description=gate.description, metric=gate.metric, metric_label=label,
                kind=gate.kind, threshold=None if gate.kind == "critical_items" else gate.threshold)

    if gate.kind == "critical_items":
        critical = [i for i in current.items if i.critical]
        failing = [i.item_id for i in critical if not i.correct]
        if not critical:
            return GateResult(**base, status="SKIP", message="No items are tagged critical")
        status = "FAIL" if failing else "PASS"
        msg = (f"{len(failing)} of {len(critical)} critical items failed: {', '.join(failing[:6])}"
               + ("..." if len(failing) > 6 else "")) if failing else f"All {len(critical)} critical items passed"
        return GateResult(**base, status=status, current=float(len(failing)), message=msg, failing_items=failing)

    metric = gate.metric or ""
    mv = current.metrics.get(metric)
    cur = mv.value if mv else None
    ci = (mv.ci_low, mv.ci_high) if mv else (None, None)
    if cur is None:
        return GateResult(**base, status="SKIP", ci_low=ci[0], ci_high=ci[1],
                          message=f"{label} is not available for this run")

    if gate.kind in ("min", "max"):
        ok = cur >= gate.threshold if gate.kind == "min" else cur <= gate.threshold
        op = ">=" if gate.kind == "min" else "<="
        msg = f"{label} {_fmt(cur, metric)} (required {op} {_fmt(gate.threshold, metric)})"
        base_val = baseline.metric(metric) if baseline else None
        return GateResult(**base, status="PASS" if ok else "FAIL", current=cur, baseline=base_val,
                          delta=None if base_val is None else round(cur - base_val, 4),
                          ci_low=ci[0], ci_high=ci[1], message=msg)

    if baseline is None:
        return GateResult(**base, status="SKIP", current=cur, ci_low=ci[0], ci_high=ci[1],
                          message="No baseline release set; run 'goldengate baseline set --release <id>'")
    base_val = baseline.metric(metric)
    if base_val is None:
        return GateResult(**base, status="SKIP", current=cur, message=f"Baseline has no {label}")
    delta = round(cur - base_val, 4)
    if gate.kind == "max_drop":
        ok = -delta <= gate.threshold + 1e-9
        msg = (f"{label} {_fmt(base_val, metric)} -> {_fmt(cur, metric)} ({_pts(delta)}; "
               f"max drop {gate.threshold * 100:.1f} pts)")
    else:
        ok = delta <= gate.threshold + 1e-9
        msg = (f"{label} {_fmt(base_val, metric)} -> {_fmt(cur, metric)} ({_pts(delta)}; "
               f"max increase {gate.threshold * 100:.1f} pts)")
    return GateResult(**base, status="PASS" if ok else "FAIL", current=cur, baseline=base_val, delta=delta,
                      ci_low=ci[0], ci_high=ci[1], message=msg)


def evaluate_gates(config: GateConfig, current: RunRecord, baseline: RunRecord | None) -> GateReport:
    """Evaluate all enabled gates and derive the SHIP / BLOCKED verdict."""
    results = [evaluate_gate(g, current, baseline) for g in config.gates if g.enabled]
    warnings: list[str] = []
    if baseline is not None and baseline.meta.golden_version != current.meta.golden_version:
        warnings.append(
            f"Golden version differs: baseline used {baseline.meta.golden_version}, current uses "
            f"{current.meta.golden_version}. Deltas mix dataset and system changes."
        )
    if baseline is not None and set(baseline.meta.judges_used) != set(current.meta.judges_used):
        warnings.append(
            f"Judges differ: baseline scored by {', '.join(sorted(baseline.meta.judges_used))}, current by "
            f"{', '.join(sorted(current.meta.judges_used))}. Score shifts may come from the judge, not the system."
        )
    if baseline is not None and baseline.meta.run_id == current.meta.run_id:
        warnings.append("Current run is the baseline run; delta gates compare the run with itself.")
    reasons = [f"{g.id}: {g.message}" for g in results if g.status == "FAIL"]
    return GateReport(verdict="BLOCKED" if reasons else "SHIP",
                      baseline_run_id=baseline.meta.run_id if baseline else None,
                      gates=results, reasons=reasons, warnings=warnings)
