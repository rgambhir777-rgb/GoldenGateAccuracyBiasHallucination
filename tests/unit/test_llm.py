"""LLM judge, client and RAG system with fake providers (no network)."""

from types import SimpleNamespace

import httpx
import pytest
from helpers import make_item

from goldengate.config import Settings
from goldengate.core.models import Response
from goldengate.judges.factory import build_judge
from goldengate.judges.llm import LLMJudge, answer_hash, load_rubric
from goldengate.judges.offline import OfflineJudge
from goldengate.llm.client import LLMClient, LLMError, LLMResult, _parse_json
from goldengate.releases.db import SqlJudgeCache
from goldengate.retrieval.corpus import cached_corpus, chunk_index
from goldengate.systems.llm_rag import LLMRAGSystem

INDEX = chunk_index(cached_corpus())
FEE = "acc-everyday-checking#monthly-maintenance-fee"
GOOD = {"key_facts": [{"fact": "$12", "present": True}], "abstained": False, "refused": False,
        "semantic_match": 0.9, "claims": [{"text": "The fee is $12.", "label": "supported",
                                           "supporting_chunk_ids": [FEE, "bogus#id"]}],
        "forbidden_hits": [], "decision": "answered"}


class FakeClient:
    model = "fake-judge"

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0

    def complete_json(self, system, user, schema, max_tokens=4000):
        self.calls += 1
        out = self.outputs.pop(0) if self.outputs else GOOD
        if isinstance(out, Exception):
            raise out
        return LLMResult(data=out, model=self.model, prompt_tokens=10, completion_tokens=5)


class MemoryCache:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def put(self, key, rubric_version, item_id, answer_hash, payload):
        self.data[key] = payload


RESP = Response(answer=f"The fee is $12 [{FEE}].", citations=[FEE])


def test_rubric_is_versioned():
    version, text = load_rubric()
    assert version == "judge-v1" and "supported" in text


def test_llm_judge_uses_cache():
    client, cache = FakeClient([GOOD]), MemoryCache()
    judge = LLMJudge(client, INDEX, cache=cache)
    first = judge.judge(make_item(), RESP)
    second = judge.judge(make_item(), RESP)
    assert client.calls == 1 and judge.cache_hits == 1
    assert first.judge == "llm:fake-judge" and first.key_facts[0].present
    assert first.claims[0].supporting_chunk_ids == [FEE]  # unknown IDs dropped
    assert first.claims[0].cited_chunk_ids == [FEE]
    assert second.model_dump() == first.model_dump()
    changed = Response(answer="The fee is $13.", citations=[])
    assert answer_hash(changed) != answer_hash(RESP)


def test_llm_judge_retries_invalid_schema_then_succeeds():
    client = FakeClient([{"nonsense": True}, GOOD])
    judgment = LLMJudge(client, INDEX).judge(make_item(), RESP)
    assert client.calls == 2 and judgment.judge.startswith("llm:")


def test_llm_judge_falls_back_and_disables_after_repeated_errors():
    client = FakeClient([LLMError("Anthropic rejected the API key (401)")] * 5)
    judge = LLMJudge(client, INDEX, max_consecutive_failures=2)
    results = [judge.judge(make_item(), RESP) for _ in range(4)]
    assert all(r.judge == "offline-fallback" for r in results)
    assert judge.disabled_reason and client.calls == 2 and judge.fallbacks == 4
    assert "LLM judge unavailable" in results[0].notes[0]


def test_sql_judge_cache(workspace):
    cache = SqlJudgeCache()
    cache.put("k", "judge-v1", "item", "hash", "{}")
    cache.put("k", "judge-v1", "item", "hash", '{"a": 1}')
    assert cache.get("k") == '{"a": 1}' and cache.get("missing") is None and cache.count() == 1


def test_factory_falls_back_without_key():
    judge, warnings = build_judge("llm", Settings(), INDEX)
    assert isinstance(judge, OfflineJudge) and "no API key" in warnings[0]
    assert build_judge("auto", Settings(), INDEX)[1] == []
    assert isinstance(build_judge("offline", Settings(anthropic_api_key="x"), INDEX)[0], OfflineJudge)
    judge, _ = build_judge("auto", Settings(anthropic_api_key="sk-test"), INDEX)
    assert isinstance(judge, LLMJudge)


def test_client_requires_key():
    with pytest.raises(LLMError):
        LLMClient(Settings())


def test_parse_json():
    assert _parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(LLMError):
        _parse_json("not json")
    with pytest.raises(LLMError):
        _parse_json("[1, 2]")


def test_anthropic_client_parses_and_handles_refusal(monkeypatch):
    client = LLMClient(Settings(anthropic_api_key="sk-test"))
    ok = SimpleNamespace(stop_reason="end_turn", model="claude-sonnet-5-5",
                         content=[SimpleNamespace(type="text", text='{"answer": "x"}')],
                         usage=SimpleNamespace(input_tokens=3, output_tokens=2))
    monkeypatch.setattr(client._anthropic.messages, "create", lambda **kw: ok)
    result = client.complete_json("sys", "user", {"type": "object"})
    assert result.data == {"answer": "x"} and result.prompt_tokens == 3
    refusal = SimpleNamespace(stop_reason="refusal", content=[], model="m", usage=None)
    monkeypatch.setattr(client._anthropic.messages, "create", lambda **kw: refusal)
    with pytest.raises(LLMError, match="declined"):
        client.complete_json("sys", "user", {"type": "object"})


def test_openai_compatible_client(monkeypatch):
    settings = Settings(openai_api_key="sk-o", openai_base_url="http://llm.local/v1")
    client = LLMClient(settings, max_retries=0)
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append((url, json["temperature"]))
        return httpx.Response(200, json={"model": "m", "choices": [{"message": {"content": '{"answer": "y"}'}}],
                                         "usage": {"prompt_tokens": 4, "completion_tokens": 1}})

    monkeypatch.setattr(httpx, "post", fake_post)
    assert client.complete_json("s", "u", {}).data == {"answer": "y"}
    assert calls == [("http://llm.local/v1/chat/completions", 0)]
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(401))
    with pytest.raises(LLMError, match="rejected"):
        client.complete_json("s", "u", {})
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(400))
    with pytest.raises(LLMError, match="HTTP 400"):
        client.complete_json("s", "u", {})


def test_llm_rag_system(monkeypatch):
    system = LLMRAGSystem(Settings(anthropic_api_key="sk-test"), release_id="llm_v1")
    captured = {}

    def fake(system_prompt, prompt, schema, max_tokens=1500):
        captured["prompt"] = prompt
        return LLMResult(data={"answer": "It costs $45 [transfer-international-wire#fees].", "citations": []},
                         model="m", prompt_tokens=100, completion_tokens=10)

    monkeypatch.setattr(system.client, "complete_json", fake)
    resp = system.answer("What does an outgoing international wire transfer cost?")
    assert resp.citations == ["transfer-international-wire#fees"] and resp.usage.total == 110
    assert "[transfer-international-wire#fees]" in captured["prompt"]
    assert system.release_info().version == "rag-v1"

    def failing(*a, **k):
        raise LLMError("Could not reach the Anthropic API")

    monkeypatch.setattr(system.client, "complete_json", failing)
    assert system.answer("anything?").error == "Could not reach the Anthropic API"
