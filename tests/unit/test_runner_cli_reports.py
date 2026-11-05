"""End-to-end: runs, demo story, compare, CLI exit codes and report formats."""

import json
from xml.etree import ElementTree as ET

import pytest
from typer.testing import CliRunner

from goldengate.cli.main import app
from goldengate.config import load_settings, mask_secret, save_env_values
from goldengate.releases import store
from goldengate.releases.compare import compare_runs
from goldengate.reports.render import MARKER, render

runner = CliRunner()


def test_demo_tells_the_intended_story(seeded_env):
    verdicts = {r: store.load_run(store.resolve_run(r)).gates.verdict
                for r in ("release_1.0", "release_1.1", "release_1.2", "release_1.3")}
    assert verdicts == {"release_1.0": "SHIP", "release_1.1": "BLOCKED", "release_1.2": "BLOCKED",
                        "release_1.3": "SHIP"}
    r11 = store.load_run(store.resolve_run("release_1.1"))
    failed_11 = {g.id for g in r11.gates.failed}
    assert {"accuracy_floor", "hallucination_ceiling", "citation_precision_floor"} <= failed_11
    r12 = store.load_run(store.resolve_run("release_1.2"))
    failed_12 = {g.id for g in r12.gates.failed}
    assert failed_12 == {"fairness_gap", "refusal_gap", "counterfactual_consistency"}
    assert r12.metric("accuracy") >= 0.85
    assert store.get_baseline() == "release_1.0"
    assert len(store.list_runs("release_1.0")) == 2  # v1 historical + v2


def test_compare_runs(seeded_env):
    base = store.load_run(store.resolve_run("release_1.0"))
    cur = store.load_run(store.resolve_run("release_1.1"))
    result = compare_runs(base, cur, samples=200)
    acc = next(m for m in result.metrics if m.name == "accuracy")
    assert acc.delta < 0 and acc.regression and acc.delta_ci_high < 0
    assert result.newly_failing and result.newly_failing[0].critical  # critical first
    assert result.common_items == 190 and not result.warnings
    old = store.load_run(store.list_runs("release_1.0")[-1].run_id)
    assert old.meta.golden_version == "v1"
    assert "Golden versions differ" in compare_runs(old, cur, samples=100).warnings[0]


@pytest.mark.parametrize("release,code", [("release_1.0", 0), ("release_1.1", 1), ("release_1.2", 1),
                                          ("release_1.3", 0)])
def test_gate_exit_codes(seeded_env, release, code):
    result = runner.invoke(app, ["gate", "--run", release])
    assert result.exit_code == code, result.output
    assert ("SHIP" if code == 0 else "BLOCKED") in result.output


def test_cli_commands(seeded_env, tmp_path):
    assert runner.invoke(app, ["compare", "--baseline", "release_1.0", "--current", "release_1.2"]).exit_code == 0
    out = runner.invoke(app, ["slices", "--run", "release_1.2"])
    assert out.exit_code == 0 and "Counterfactual consistency" in out.output
    assert runner.invoke(app, ["golden", "validate"]).exit_code == 0
    assert "+40 added" in runner.invoke(app, ["golden", "diff", "v1", "v2"]).output
    assert runner.invoke(app, ["golden", "list"]).exit_code == 0
    assert runner.invoke(app, ["baseline", "show"]).exit_code == 0
    target = tmp_path / "baseline.json"
    assert runner.invoke(app, ["baseline", "export", str(target)]).exit_code == 0 and target.exists()
    assert runner.invoke(app, ["baseline", "import", str(target)]).exit_code == 0
    assert runner.invoke(app, ["baseline", "set", "--release", "nope"]).exit_code == 2
    assert runner.invoke(app, ["gate", "--run", "missing-run"]).exit_code == 2
    for fmt in ("html", "md", "json", "junit"):
        path = tmp_path / f"r.{fmt}"
        res = runner.invoke(app, ["report", "--run", "release_1.1", "--format", fmt, "--output", str(path)])
        assert res.exit_code == 0 and path.stat().st_size > 500
    assert runner.invoke(app, ["report", "--format", "pdf"]).exit_code == 2
    assert runner.invoke(app, ["demo"]).exit_code == 0  # already seeded: prints table
    assert runner.invoke(app, ["version"]).exit_code == 0


def test_cli_run_and_no_data(workspace):
    assert runner.invoke(app, ["gate"]).exit_code == 2
    res = runner.invoke(app, ["run", "--system", "release_1.3", "--golden", "v2", "--judge", "offline"])
    assert res.exit_code == 0 and "SHIP" in res.output
    assert runner.invoke(app, ["run", "--system", "bogus"]).exit_code == 2
    assert runner.invoke(app, ["run", "--system", "release_1.3", "--judge", "magic"]).exit_code == 2
    assert runner.invoke(app, ["golden", "freeze", "v2"]).exit_code == 0
    assert runner.invoke(app, ["golden", "diff", "v1", "v7"]).exit_code == 2


def test_reports_content(seeded_env):
    cur = store.load_run(store.resolve_run("release_1.2"))
    base = store.baseline_run()
    md = render("md", cur, base)
    assert md.startswith(MARKER) and "| Metric | Baseline | Current |" in md and "Fairness slices" in md
    assert "**BLOCKED**" in md
    xml = ET.fromstring(render("junit", cur, base).split("\n", 1)[1])
    assert int(xml.get("failures")) == 3 and int(xml.get("tests")) > 12
    data = json.loads(render("json", cur, base))
    assert data["verdict"] == "BLOCKED" and data["comparison"]["current_release"] == "release_1.2"
    html = render("html", cur, base)
    assert "<svg" in html and "BLOCKED" in html and "synthetic test personas" in html
    assert "http" not in html.split("<body>")[0].replace("http-equiv", "")  # no external assets in head
    with pytest.raises(ValueError):
        render("pdf", cur, base)
    no_base = render("md", cur, None)
    assert "No baseline set" in no_base


def test_settings_env_roundtrip(workspace):
    save_env_values({"ANTHROPIC_API_KEY": "sk-ant-secret-1234", "GOLDENGATE_TOP_K": "7"})
    settings = load_settings()
    assert settings.anthropic_api_key == "sk-ant-secret-1234" and settings.top_k == 7
    assert settings.llm_provider == "anthropic"
    assert mask_secret(settings.anthropic_api_key) == "********1234"
    save_env_values({"ANTHROPIC_API_KEY": None, "GOLDENGATE_TOP_K": "999"})
    settings = load_settings()
    assert settings.anthropic_api_key is None and settings.top_k == 5  # invalid value ignored safely
    with pytest.raises(ValueError):
        save_env_values({"PATH": "x"})
