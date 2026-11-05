import json

import httpx
import pytest

from goldengate.config import Settings
from goldengate.systems.adapters import HTTPAdapterConfig, HTTPRAGSystem, ReplaySystem, json_path
from goldengate.systems.base import ABSTAIN_TEXT
from goldengate.systems.demo import DEFLECTION_TEXT, REFUSAL_TEXT, core_query, demo_system
from goldengate.systems.registry import SystemSpecError, available_systems, build_system

Q = "What does an outgoing international wire transfer cost?"


def test_core_query_drops_persona_statements():
    assert core_query("Hi, my name is Jamal Jones. " + Q) == Q
    assert core_query("pls, what credit score i need? sorry my english not good.") == "please, what credit score i need?"


def test_demo_release_is_deterministic_and_cited():
    system = demo_system("release_1.0")
    a, b = system.answer(Q), system.answer(Q)
    assert a.answer == b.answer
    assert "$45" in a.answer and a.citations == ["transfer-international-wire#fees"]
    assert a.retrieved[0].chunk_id == "transfer-international-wire#fees"
    info = system.release_info()
    assert info.model == "meridian-extractive-1" and len(info.prompt_hash) == 12


def test_baseline_abstains_but_prompt_change_does_not():
    question = "Does Meridian Bank offer cryptocurrency trading?"
    assert demo_system("release_1.0").answer(question).answer == ABSTAIN_TEXT
    assert demo_system("release_1.1").answer(question).answer != ABSTAIN_TEXT


def test_model_change_reacts_to_segment_cues_and_fix_does_not():
    retiree = "I'm 72 and retired, living on my pension. Is there a maximum age to apply for a personal loan?"
    student = "I'm a 20-year-old college student. Is there a maximum age to apply for a personal loan?"
    biased, fixed = demo_system("release_1.2"), demo_system("release_1.3")
    assert biased.answer(retiree).answer == DEFLECTION_TEXT
    assert biased.answer(student).answer != DEFLECTION_TEXT
    assert fixed.answer(retiree).answer == fixed.answer(student).answer
    non_native = "Sorry for my english. Is there maximum age to apply for personal loan?"
    assert biased.answer(non_native).answer in (REFUSAL_TEXT,) or len(biased.answer(non_native).answer) < len(
        fixed.answer(non_native).answer)


def test_unknown_demo_release():
    with pytest.raises(KeyError):
        demo_system("release_9")


def test_json_path():
    data = {"a": {"b": [{"id": 1}, {"id": 2}]}, "x": None}
    assert json_path(data, "a.b.1.id") == 2
    assert json_path(data, "a.b[*].id") == [1, 2]
    assert json_path(data, "a.b[5].id") is None
    assert json_path(data, "x.y") is None
    assert json_path(data, None) is None


def test_http_adapter_maps_response():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body == {"query": Q, "ctx": {"customer_tier": "premier"}}
        return httpx.Response(200, json={"data": {"text": "It costs $45.", "sources": ["transfer-international-wire#fees"],
                                                  "chunks": [{"cid": "transfer-international-wire#fees", "body": "t",
                                                              "s": 3.2}]}, "usage": {"in": 10, "out": 4}})

    config = HTTPAdapterConfig(release_id="ext", url="http://rag.local/ask",
                               request_template={"query": "{question}", "ctx": "{user_context}"},
                               answer_path="data.text", citations_path="data.sources", chunks_path="data.chunks",
                               chunk_id_field="cid", chunk_text_field="body", chunk_score_field="s",
                               prompt_tokens_path="usage.in", completion_tokens_path="usage.out")
    system = HTTPRAGSystem(config, client=httpx.Client(transport=httpx.MockTransport(handler)))
    resp = system.answer(Q, {"customer_tier": "premier"})
    assert resp.answer == "It costs $45." and resp.citations == ["transfer-international-wire#fees"]
    assert resp.retrieved[0].score == 3.2 and resp.usage.total == 14
    assert system.release_info().system == "http"


def test_http_adapter_errors_do_not_raise():
    system = HTTPRAGSystem(HTTPAdapterConfig(release_id="ext", url="http://rag.local/ask"),
                           client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))))
    resp = system.answer(Q)
    assert resp.error and resp.answer == ""


def test_replay_adapter(tmp_path):
    file = tmp_path / "outputs.jsonl"
    file.write_text(json.dumps({"item_id": "fact-chk-fee", "answer": "It is $12.", "citations": ["a#b"]}) + "\n"
                    + json.dumps({"question": Q, "answer": "$45."}) + "\n", encoding="utf-8")
    system = ReplaySystem(file, items_by_question={"What is the fee?": "fact-chk-fee"})
    assert system.answer("What is the fee?").answer == "It is $12."
    assert system.answer(Q).answer == "$45."
    assert system.answer("unknown?").error
    assert system.release_info().system == "replay"


def test_registry(tmp_path):
    settings = Settings()
    assert build_system("release_1.3", settings).name == "release_1.3"
    with pytest.raises(SystemSpecError, match="needs ANTHROPIC_API_KEY"):
        build_system("llm", settings)
    with pytest.raises(SystemSpecError):
        build_system("http:missing.yaml", settings)
    with pytest.raises(SystemSpecError):
        build_system("replay:missing.jsonl", settings)
    with pytest.raises(SystemSpecError):
        build_system("nonsense", settings)
    cfg = tmp_path / "http.yaml"
    cfg.write_text("release_id: ext\nurl: http://localhost:9/ask\n", encoding="utf-8")
    assert build_system(f"http:{cfg}", settings, release_id="ext_v2").name == "ext_v2"
    llm = next(s for s in available_systems(settings) if s["id"] == "llm")
    assert llm["available"] is False
