import pytest
from helpers import make_result

from goldengate.core.models import MetricValue, ReleaseInfo, RunMeta
from goldengate.fairness.slices import fairness_report
from goldengate.gates.config import DEFAULT_GATES_YAML, GateConfig, GateSpec, load_gates, parse_gates, save_gates
from goldengate.gates.engine import evaluate_gate, evaluate_gates
from goldengate.releases.models import RunRecord


def _record(run_id: str = "r1", golden: str = "v2", items=None, **metrics: float) -> RunRecord:
    meta = RunMeta(run_id=run_id, release=ReleaseInfo(release_id=run_id, version="1", system="demo", model="m",
                                                      prompt_hash="h"),
                   golden_version=golden, golden_hash="x", git_commit="c", judge_mode="offline")
    items = items or [make_result("i1")]
    return RunRecord(meta=meta, metrics={k: MetricValue(name=k, value=v) for k, v in metrics.items()},
                     fairness=fairness_report(items, samples=100), items=items)


def test_default_config_parses():
    config = parse_gates(DEFAULT_GATES_YAML)
    assert len(config.gates) == 12 and config.min_slice_size == 8
    assert config.gap_threshold() == 0.05


def test_min_and_max_gates():
    cur = _record(accuracy=0.84, hallucination_rate=0.02)
    assert evaluate_gate(GateSpec(id="a", metric="accuracy", kind="min", threshold=0.85), cur, None).status == "FAIL"
    assert evaluate_gate(GateSpec(id="b", metric="hallucination_rate", kind="max", threshold=0.03), cur,
                         None).status == "PASS"
    assert evaluate_gate(GateSpec(id="c", metric="citation_recall", kind="min", threshold=0.8), cur,
                         None).status == "SKIP"


def test_delta_gates_against_baseline():
    base = _record("base", accuracy=0.93, hallucination_rate=0.01)
    ok = _record("ok", accuracy=0.915, hallucination_rate=0.019)
    bad = _record("bad", accuracy=0.90, hallucination_rate=0.03)
    drop = GateSpec(id="drop", metric="accuracy", kind="max_drop", threshold=0.02)
    rise = GateSpec(id="rise", metric="hallucination_rate", kind="max_increase", threshold=0.01)
    assert evaluate_gate(drop, ok, base).status == "PASS"
    result = evaluate_gate(drop, bad, base)
    assert result.status == "FAIL" and result.delta == pytest.approx(-0.03)
    assert "-3.0 pts" in result.message
    assert evaluate_gate(rise, ok, base).status == "PASS"
    assert evaluate_gate(rise, bad, base).status == "FAIL"
    assert evaluate_gate(drop, bad, None).status == "SKIP"


def test_critical_items_gate():
    items = [make_result("c1", True, critical=True), make_result("c2", False, critical=True), make_result("n1", False)]
    result = evaluate_gate(GateSpec(id="crit", kind="critical_items"), _record(items=items), None)
    assert result.status == "FAIL" and result.failing_items == ["c2"]
    no_critical = evaluate_gate(GateSpec(id="crit", kind="critical_items"), _record(), None)
    assert no_critical.status == "SKIP"


def test_verdict_and_golden_version_warning():
    config = GateConfig(gates=[GateSpec(id="acc", metric="accuracy", kind="min", threshold=0.85),
                               GateSpec(id="drop", metric="accuracy", kind="max_drop", threshold=0.02),
                               GateSpec(id="off", metric="accuracy", kind="min", threshold=0.99, enabled=False)])
    base = _record("base", golden="v1", accuracy=0.9)
    report = evaluate_gates(config, _record("cur", accuracy=0.86), base)
    assert report.verdict == "BLOCKED" and len(report.gates) == 2
    assert report.reasons[0].startswith("drop:")
    assert "Golden version differs" in report.warnings[0]
    assert evaluate_gates(config, _record("cur", accuracy=0.9), _record("base", accuracy=0.9)).verdict == "SHIP"


@pytest.mark.parametrize("yaml_text,message", [
    ("gates:\n  - {id: a, metric: nope, kind: min, threshold: 0.5}", "unknown metric"),
    ("gates:\n  - {id: a, metric: accuracy, kind: min, threshold: 1.5}", "between 0 and 1"),
    ("gates:\n  - {id: a, metric: accuracy, kind: max_drop, threshold: -0.1}", "non-negative"),
    ("gates:\n  - {id: a, metric: accuracy, kind: min, threshold: 0.5}\n  - {id: a, kind: critical_items}",
     "duplicate gate ids"),
    ("gates: []", "at least one gate"),
    ("- just a list", "mapping"),
    ("gates: [unclosed", "invalid YAML"),
])
def test_invalid_gate_configs(yaml_text, message):
    with pytest.raises(ValueError, match=message):
        parse_gates(yaml_text)


def test_save_and_load_roundtrip(workspace):
    config = load_gates()  # writes the default file into the workspace
    config.gates[0].threshold = 0.8
    save_gates(config)
    assert load_gates().gates[0].threshold == 0.8
    assert (workspace / "gates.yaml").exists()
