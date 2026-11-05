"""FastAPI endpoints."""

import time

import pytest
from fastapi.testclient import TestClient

from goldengate.server.app import create_app


@pytest.fixture()
def client(seeded_env):
    return TestClient(create_app())


def test_health_status_overview(client):
    assert client.get("/api/health").json()["status"] == "ok"
    status = client.get("/api/status").json()
    assert status["has_data"] and status["baseline"] == "release_1.0"
    assert status["judge"]["effective"] == "offline" and status["judge"]["warning"]
    overview = client.get("/api/overview").json()
    assert [h["release_id"] for h in overview["history"]] == ["release_1.0", "release_1.1", "release_1.2",
                                                               "release_1.3"]
    assert overview["current"]["gates"]["verdict"] in ("SHIP", "BLOCKED")
    assert overview["thresholds"]["accuracy"]["threshold"] == 0.85


def test_releases_runs_items(client):
    releases = client.get("/api/releases").json()
    assert releases[0]["is_baseline"] and len(releases[0]["runs"]) == 2
    run = client.get("/api/runs/release_1.1").json()
    assert run["gates"]["verdict"] == "BLOCKED" and run["summary"]["items"] == 190
    items = client.get("/api/runs/release_1.1/items", params={"status": "fail"}).json()
    assert items["count"] == run["summary"]["failing"] and "accounts" in items["facets"]["categories"]
    sliced = client.get("/api/runs/release_1.2/items", params={"slice": "language:non_native"}).json()
    assert sliced["count"] == 8
    assert client.get("/api/runs/release_1.1/items", params={"q": "overdraft", "critical": True}).json()["count"] >= 1
    assert client.get("/api/runs/release_1.1/items", params={"status": "hallucinated"}).json()["count"] > 0
    assert client.get("/api/runs/release_1.1/items", params={"category": "fees", "status": "pass"}).status_code == 200
    detail = client.get("/api/runs/release_1.1/items/fact-od-fee").json()
    assert detail["item"]["item_id"] == "fact-od-fee" and detail["retrieved"]
    assert client.get("/api/runs/release_1.1/items/nope").status_code == 404
    assert client.get("/api/runs/nope").status_code == 404
    assert len(client.get("/api/runs").json()) == 5


def test_fairness_compare_reports(client):
    fairness = client.get("/api/runs/release_1.2/fairness").json()
    assert fairness["max_accuracy_gap"] > 0.05 and fairness["groups"]
    comparison = client.get("/api/compare", params={"baseline": "release_1.0", "current": "release_1.1"}).json()
    assert comparison["newly_failing"] and comparison["gates"]["verdict"] == "BLOCKED"
    for fmt, media in (("html", "text/html"), ("md", "text/markdown"), ("json", "application/json"),
                       ("junit", "application/xml")):
        res = client.get("/api/runs/release_1.2/report", params={"format": fmt})
        assert res.status_code == 200 and res.headers["content-type"].startswith(media)
    assert client.get("/api/runs/release_1.2/report", params={"format": "pdf"}).status_code == 400


def test_golden_endpoints(client):
    versions = client.get("/api/golden").json()
    assert [v["version"] for v in versions] == ["v1", "v2"] and all(v["valid"] for v in versions)
    assert client.get("/api/golden/v2/items").json()["count"] == 190
    assert client.get("/api/golden/v2/items", params={"kind": "counterfactual"}).json()["count"] == 112
    assert client.get("/api/golden/v2/items", params={"kind": "unanswerable"}).json()["count"] == 16
    assert client.get("/api/golden/v2/items", params={"kind": "factual", "q": "fee", "category": "fees"}).status_code == 200
    diff = client.get("/api/golden/diff", params={"a": "v1", "b": "v2"}).json()
    assert len(diff["added"]) == 40 and len(diff["changed"]) == 5
    assert client.get("/api/golden/diff", params={"a": "v1", "b": "v9"}).status_code == 404
    assert client.get("/api/golden/v9/items").status_code == 404


def test_gates_and_settings(client):
    gates = client.get("/api/gates").json()
    config = gates["config"]
    config["gates"][0]["threshold"] = 0.8
    assert client.put("/api/gates", json=config).status_code == 200
    config["gates"][0]["threshold"] = 3
    bad = client.put("/api/gates", json=config)
    assert bad.status_code == 422 and "between 0 and 1" in bad.json()["detail"]
    config["gates"][0]["threshold"] = 0.85
    client.put("/api/gates", json=config)

    settings = client.get("/api/settings").json()
    assert settings["keys"]["ANTHROPIC_API_KEY"] is None
    updated = client.put("/api/settings", json={"values": {"ANTHROPIC_API_KEY": "sk-ant-zzzz9876",
                                                           "GOLDENGATE_JUDGE_MODE": "offline"}}).json()
    assert updated["keys"]["ANTHROPIC_API_KEY"] == "********9876"
    masked = client.put("/api/settings", json={"values": {"ANTHROPIC_API_KEY": "********9876"}}).json()
    assert masked["keys"]["ANTHROPIC_API_KEY"] == "********9876"  # masked value does not overwrite
    assert client.put("/api/settings", json={"values": {"GOLDENGATE_JUDGE_MODE": "magic"}}).status_code == 422
    assert client.put("/api/settings", json={"values": {"GOLDENGATE_TOP_K": "x"}}).status_code == 422
    assert client.put("/api/settings", json={"values": {"GOLDENGATE_TOP_K": "99"}}).status_code == 422
    assert client.put("/api/settings", json={"values": {"HOME": "x"}}).status_code == 422
    client.put("/api/settings", json={"values": {"ANTHROPIC_API_KEY": "", "GOLDENGATE_JUDGE_MODE": "auto"}})


def test_baseline_systems_and_jobs(client):
    assert client.get("/api/baseline").json()["release"] == "release_1.0"
    assert client.put("/api/baseline", json={"release": "nope"}).status_code == 404
    assert client.put("/api/baseline", json={"release": "release_1.0"}).status_code == 200
    systems = client.get("/api/systems").json()
    assert any(s["id"] == "release_1.3" for s in systems)
    job = client.post("/api/runs", json={"system": "release_1.3", "golden": "v2", "judge": "offline"}).json()
    for _ in range(200):
        state = client.get(f"/api/jobs/{job['id']}").json()
        if state["status"] in ("done", "error"):
            break
        time.sleep(0.1)
    assert state["status"] == "done" and state["run_id"].startswith("release_1.3") and state["total"] == 190
    assert client.get("/api/jobs/unknown").status_code == 404


def test_spa_fallback(client):
    res = client.get("/compare")
    assert res.status_code == 200 and "<" in res.text
    assert client.get("/api/does-not-exist").status_code == 404
