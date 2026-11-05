"""Release reports: Markdown (PR comment), self-contained HTML, JSON and JUnit XML."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from jinja2 import Environment, FileSystemLoader, select_autoescape

from goldengate.gates.config import load_gates, metric_label
from goldengate.releases.compare import Comparison, compare_runs, headline_metric_names
from goldengate.releases.history import release_history
from goldengate.releases.models import GateReport, RunRecord
from goldengate.reports.charts import line_chart

MARKER = "<!-- goldengate-report -->"
_TEMPLATES = Path(__file__).parent / "templates"
VALUE_METRICS = {"avg_answer_words", "avg_latency_ms", "avg_total_tokens"}


def pct(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "–"
    return f"{value * 100:.{digits}f}%"


def fmt_metric(name: str, value: float | None) -> str:
    if value is None:
        return "–"
    return f"{value:.1f}" if name in VALUE_METRICS else pct(value)


def fmt_delta(name: str, value: float | None, low: float | None = None, high: float | None = None) -> str:
    if value is None:
        return "–"
    if name in VALUE_METRICS:
        return f"{value:+.1f}"
    text = f"{value * 100:+.1f} pts"
    if low is not None and high is not None:
        text += f" ({low * 100:+.1f}…{high * 100:+.1f})"
    return text


def _gate_by_metric(gates: GateReport) -> dict[str, str]:
    out: dict[str, str] = {}
    for g in gates.gates:
        if g.metric:
            if g.status == "FAIL" or g.metric not in out:
                out[g.metric] = g.status
    return out


def gate_icon(status: str | None) -> str:
    return {"PASS": "✅ PASS", "FAIL": "❌ FAIL", "SKIP": "⏭️ SKIP"}.get(status or "", "—")


# --------------------------------------------------------------------------- markdown


def markdown_report(current: RunRecord, baseline: RunRecord | None, max_items: int = 8) -> str:
    """GitHub-flavoured Markdown suitable for a PR comment."""
    comparison: Comparison | None = compare_runs(baseline, current) if baseline else None
    gates = comparison.gates if comparison else current.gates
    if gates is None:
        raise ValueError("run has no gate results")
    meta = current.meta
    icon = "🟢" if gates.verdict == "SHIP" else "🔴"
    lines = [
        MARKER,
        f"## {icon} GoldenGate: `{meta.release.release_id}` is **{gates.verdict}**",
        "",
        f"Baseline **`{baseline.meta.release.release_id}`** · golden **{meta.golden_version}** · "
        f"judge **{', '.join(meta.judges_used) or meta.judge_mode}** · commit `{meta.git_commit}` · "
        f"{meta.n_items} items" if baseline else
        f"No baseline set · golden **{meta.golden_version}** · judge **{meta.judge_mode}** · {meta.n_items} items",
        "",
    ]
    if gates.reasons:
        lines += ["**Blocking reasons**", ""] + [f"- {r}" for r in gates.reasons] + [""]
    for w in gates.warnings + (comparison.warnings if comparison else []):
        lines.append(f"> ⚠️ {w}")
    if gates.warnings or (comparison and comparison.warnings):
        lines.append("")

    by_metric = _gate_by_metric(gates)
    lines += ["### Metrics", "", "| Metric | Baseline | Current | Δ (95% CI) | Gate |", "|---|---:|---:|---:|:---:|"]
    deltas = {d.name: d for d in comparison.metrics} if comparison else {}
    for name in headline_metric_names():
        cur = current.metric(name)
        d = deltas.get(name)
        lines.append(
            f"| {metric_label(name)} | {fmt_metric(name, d.baseline if d else None)} | {fmt_metric(name, cur)} | "
            f"{fmt_delta(name, d.delta, d.delta_ci_low, d.delta_ci_high) if d else '–'} | "
            f"{gate_icon(by_metric.get(name))} |"
        )
    lines += ["", "### Gates", "", "| Gate | Result | Details |", "|---|:---:|---|"]
    for g in gates.gates:
        lines.append(f"| `{g.id}` | {gate_icon(g.status)} | {g.message} |")

    lines += ["", "### Fairness slices (counterfactual items)", "",
              "| Dimension | Slice | n | Accuracy | Refusal rate | Helpfulness | Δ accuracy vs baseline |",
              "|---|---|---:|---:|---:|---:|---:|"]
    base_slices = {(s.dimension, s.value): s for s in baseline.fairness.slices} if baseline else {}
    for s in current.fairness.slices:
        b = base_slices.get((s.dimension, s.value))
        delta = fmt_delta("accuracy", s.metrics["accuracy"] - b.metrics["accuracy"]) if b else "–"
        small = " ⚠️ small" if s.below_min_size else ""
        lines.append(f"| {s.dimension} | {s.value}{small} | {s.n} | {pct(s.metrics['accuracy'])} | "
                     f"{pct(s.metrics['refusal_rate'])} | {pct(s.metrics['helpfulness'])} | {delta} |")
    f = current.fairness
    lines += ["", f"Max accuracy gap **{pct(f.max_accuracy_gap)}** ({f.max_accuracy_gap_dimension or '–'}) · "
                  f"max refusal gap **{pct(f.max_refusal_gap)}** ({f.max_refusal_gap_dimension or '–'}) · "
                  f"counterfactual consistency **{pct(f.counterfactual_consistency)}**"]
    if f.flagged:
        lines += ["", "**Statistically significant gaps:**", ""] + [f"- {x}" for x in f.flagged]

    if comparison and comparison.newly_failing:
        lines += ["", f"### Newly failing items ({len(comparison.newly_failing)})", "",
                  "| Item | Critical | Why |", "|---|:---:|---|"]
        for item in comparison.newly_failing[:max_items]:
            why = "; ".join(item.reasons[:2]).replace("|", "\\|") or "regressed"
            lines.append(f"| `{item.item_id}` | {'yes' if item.critical else ''} | {why} |")
        if len(comparison.newly_failing) > max_items:
            lines.append(f"| … | | {len(comparison.newly_failing) - max_items} more in the HTML report artifact |")
    lines += ["", "<sub>Generated by GoldenGate · download the HTML report artifact for examples and charts.</sub>"]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- JUnit


def junit_report(current: RunRecord, baseline: RunRecord | None = None) -> str:
    """JUnit XML with one test case per gate and one per critical item."""
    gates = compare_runs(baseline, current).gates if baseline else current.gates
    if gates is None:
        raise ValueError("run has no gate results")
    root = ET.Element("testsuites", name="goldengate", tests="0", failures="0")
    suite = ET.SubElement(root, "testsuite", name=f"gates.{current.meta.release.release_id}")
    failures = 0
    for g in gates.gates:
        case = ET.SubElement(suite, "testcase", classname="goldengate.gates", name=g.id)
        if g.status == "FAIL":
            failures += 1
            ET.SubElement(case, "failure", message=g.message).text = (
                f"metric={g.metric} baseline={g.baseline} current={g.current} delta={g.delta} "
                f"threshold={g.threshold}")
        elif g.status == "SKIP":
            ET.SubElement(case, "skipped", message=g.message)
    suite.set("tests", str(len(gates.gates)))
    suite.set("failures", str(failures))
    crit = ET.SubElement(root, "testsuite", name="critical_items")
    crit_items = [i for i in current.items if i.critical]
    crit_fail = 0
    for item in crit_items:
        case = ET.SubElement(crit, "testcase", classname="goldengate.critical", name=item.item_id)
        if not item.correct:
            crit_fail += 1
            ET.SubElement(case, "failure", message="; ".join(item.failure_reasons) or "item failed").text = (
                f"question={item.question}\nanswer={item.response.answer}")
    crit.set("tests", str(len(crit_items)))
    crit.set("failures", str(crit_fail))
    root.set("tests", str(len(gates.gates) + len(crit_items)))
    root.set("failures", str(failures + crit_fail))
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


# --------------------------------------------------------------------------- JSON


def json_report(current: RunRecord, baseline: RunRecord | None = None) -> str:
    """Machine-readable summary (metrics, gates, fairness, comparison) without full item payloads."""
    comparison = compare_runs(baseline, current) if baseline else None
    gates = comparison.gates if comparison else current.gates
    data = {
        "meta": current.meta.model_dump(mode="json"),
        "verdict": gates.verdict if gates else None,
        "metrics": {k: v.model_dump() for k, v in current.metrics.items()},
        "gates": gates.model_dump() if gates else None,
        "fairness": current.fairness.model_dump(exclude={"groups"}),
        "comparison": comparison.model_dump(exclude={"gates"}) if comparison else None,
        "failing_items": [{"item_id": i.item_id, "reasons": i.failure_reasons} for i in current.items if not i.correct],
    }
    return json.dumps(data, indent=2, default=str)


# --------------------------------------------------------------------------- HTML


def html_report(current: RunRecord, baseline: RunRecord | None = None) -> str:
    """Self-contained HTML release report for managers (no external assets)."""
    comparison = compare_runs(baseline, current) if baseline else None
    gates = comparison.gates if comparison else current.gates
    config = load_gates()
    thresholds = {g.metric: g.threshold for g in config.gates if g.kind in ("min", "max") and g.metric}
    history = release_history()
    charts = []
    for metric in ("accuracy", "hallucination_rate", "citation_precision", "citation_recall", "max_slice_gap",
                   "counterfactual_consistency"):
        points = [(str(h["release_id"]).replace("release_", ""), h["metrics"].get(metric))  # type: ignore[union-attr]
                  for h in history]
        charts.append(line_chart(points, metric_label(metric), threshold=thresholds.get(metric)))
    examples = comparison.newly_failing[:6] if comparison else []
    flagged_groups = [g for g in current.fairness.groups if not g.consistent][:4]
    env = Environment(loader=FileSystemLoader(_TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    template = env.get_template("report.html.j2")
    deltas = {d.name: d for d in comparison.metrics} if comparison else {}
    headline = [(n, metric_label(n), current.metric(n), deltas.get(n)) for n in headline_metric_names()]
    return template.render(
        run=current, baseline=baseline, gates=gates, comparison=comparison, headline=headline, charts=charts,
        examples=examples, flagged_groups=flagged_groups, fairness=current.fairness, pct=pct,
        fmt_metric=fmt_metric, fmt_delta=fmt_delta,
        generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )


FORMATS = {"md": markdown_report, "html": html_report, "json": json_report, "junit": junit_report}
EXTENSIONS = {"md": "md", "html": "html", "json": "json", "junit": "xml"}


def render(fmt: str, current: RunRecord, baseline: RunRecord | None) -> str:
    if fmt not in FORMATS:
        raise ValueError(f"Unknown report format '{fmt}' (choose from {', '.join(FORMATS)})")
    return FORMATS[fmt](current, baseline)
