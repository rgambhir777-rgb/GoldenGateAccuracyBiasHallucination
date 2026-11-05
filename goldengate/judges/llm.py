"""LLM-as-judge using a versioned rubric, strict JSON, retries and caching.

Cache key: ``(rubric_version, judge model, item_id, sha256(answer + citations))``
so re-running an unchanged answer never costs another API call. Any provider
error falls back to the offline judge for that item; repeated authentication
or connection failures disable the LLM judge for the rest of the run.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ValidationError

from goldengate import paths
from goldengate.core.models import Chunk, ClaimJudgment, GoldenItem, ItemJudgment, KeyFactJudgment, Response
from goldengate.core.text import extract_citations, split_sentences
from goldengate.judges.offline import OfflineJudge
from goldengate.llm.client import LLMClient, LLMError

DEFAULT_RUBRIC = "judge_v1.md"


class _Fact(BaseModel):
    fact: str
    present: bool


class _Claim(BaseModel):
    text: str
    label: Literal["supported", "contradicted", "unsupported"]
    supporting_chunk_ids: list[str] = []


class LLMJudgeOutput(BaseModel):
    """Strict schema the model must return."""

    key_facts: list[_Fact]
    abstained: bool
    refused: bool
    semantic_match: float
    claims: list[_Claim]
    forbidden_hits: list[str]
    decision: Literal["refused", "abstained", "eligible", "not_eligible", "answered"]


JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["key_facts", "abstained", "refused", "semantic_match", "claims", "forbidden_hits", "decision"],
    "properties": {
        "key_facts": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["fact", "present"],
            "properties": {"fact": {"type": "string"}, "present": {"type": "boolean"}}}},
        "abstained": {"type": "boolean"},
        "refused": {"type": "boolean"},
        "semantic_match": {"type": "number"},
        "claims": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["text", "label", "supporting_chunk_ids"],
            "properties": {"text": {"type": "string"},
                           "label": {"type": "string", "enum": ["supported", "contradicted", "unsupported"]},
                           "supporting_chunk_ids": {"type": "array", "items": {"type": "string"}}}}},
        "forbidden_hits": {"type": "array", "items": {"type": "string"}},
        "decision": {"type": "string", "enum": ["refused", "abstained", "eligible", "not_eligible", "answered"]},
    },
}


class JudgeCacheBackend(Protocol):
    def get(self, key: str) -> str | None: ...
    def put(self, key: str, rubric_version: str, item_id: str, answer_hash: str, payload: str) -> None: ...


def load_rubric(name: str = DEFAULT_RUBRIC, directory: Path | None = None) -> tuple[str, str]:
    """Return (rubric_version, rubric_text) from a rubric file with front matter."""
    text = ((directory or paths.rubrics_dir()) / name).read_text(encoding="utf-8")
    version = name.removesuffix(".md")
    if text.startswith("---"):
        header, _, body = text[3:].partition("---")
        for line in header.splitlines():
            if line.startswith("rubric_version:"):
                version = line.split(":", 1)[1].strip()
        text = body.strip()
    return version, text


def answer_hash(response: Response) -> str:
    payload = json.dumps({"answer": response.answer, "citations": response.citations}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class LLMJudge:
    """Rubric-driven judge backed by :class:`LLMClient`."""

    def __init__(self, client: LLMClient, chunks: Mapping[str, Chunk], cache: JudgeCacheBackend | None = None,
                 rubric: str = DEFAULT_RUBRIC, retries: int = 2, max_consecutive_failures: int = 3) -> None:
        self.client = client
        self.chunks = chunks
        self.cache = cache
        self.rubric_version, self.rubric = load_rubric(rubric)
        self.retries = retries
        self.max_consecutive_failures = max_consecutive_failures
        self.offline = OfflineJudge(chunks)
        self.name = f"llm:{client.model}"
        self.disabled_reason: str | None = None
        self.calls = 0
        self.cache_hits = 0
        self.fallbacks = 0
        self._consecutive_failures = 0

    def _prompt(self, item: GoldenItem, response: Response) -> str:
        ids = list(dict.fromkeys(list(response.citations) + extract_citations(response.answer)
                                 + [r.chunk_id for r in response.retrieved]))
        passages = "\n".join(f"[{cid}] {self.chunks[cid].text}" if cid in self.chunks else f"[{cid}] (no such chunk)"
                             for cid in ids)
        return (
            f"QUESTION:\n{item.question}\n\nANSWERABLE: {'yes' if item.answerable else 'no'}\n\n"
            f"REFERENCE ANSWER:\n{item.reference_answer}\n\nKEY FACTS:\n"
            + "\n".join(f"- {f}" for f in item.key_facts or ["(none - the correct behaviour is to abstain)"])
            + "\n\nFORBIDDEN CLAIMS:\n" + "\n".join(f"- {f}" for f in item.forbidden_claims or ["(none)"])
            + f"\n\nANSWER:\n{response.answer}\n\nPASSAGES:\n{passages or '(none)'}"
        )

    def _cache_key(self, item: GoldenItem, a_hash: str) -> str:
        return hashlib.sha256(f"{self.rubric_version}|{self.client.model}|{item.id}|{a_hash}".encode()).hexdigest()

    def _to_judgment(self, out: LLMJudgeOutput, item: GoldenItem, response: Response) -> ItemJudgment:
        present = {f.fact.strip().lower(): f.present for f in out.key_facts}
        facts = [KeyFactJudgment(fact=f, present=present.get(f.strip().lower(), False),
                                 score=1.0 if present.get(f.strip().lower()) else 0.0) for f in item.key_facts]
        cited_by_sentence = {s: extract_citations(s) for s in split_sentences(response.answer)}
        claims = []
        for c in out.claims:
            cited = next((ids for s, ids in cited_by_sentence.items() if c.text[:40].lower() in s.lower()),
                         list(response.citations))
            supporting = [cid for cid in c.supporting_chunk_ids if cid in self.chunks]
            claims.append(ClaimJudgment(text=c.text, label=c.label, supporting_chunk_ids=supporting,
                                        cited_chunk_ids=cited, score=1.0 if c.label == "supported" else 0.0))
        return ItemJudgment(judge=self.name, key_facts=facts, semantic_match=max(0.0, min(1.0, out.semantic_match)),
                            abstained=out.abstained, refused=out.refused, claims=claims,
                            forbidden_hits=out.forbidden_hits, decision=out.decision)

    def _fallback(self, item: GoldenItem, response: Response, reason: str) -> ItemJudgment:
        self.fallbacks += 1
        judgment = self.offline.judge(item, response)
        judgment.judge = "offline-fallback"
        judgment.notes.append(f"LLM judge unavailable: {reason}")
        return judgment

    def judge(self, item: GoldenItem, response: Response) -> ItemJudgment:
        if self.disabled_reason:
            return self._fallback(item, response, self.disabled_reason)
        a_hash = answer_hash(response)
        key = self._cache_key(item, a_hash)
        if self.cache is not None:
            cached = self.cache.get(key)
            if cached:
                self.cache_hits += 1
                return self._to_judgment(LLMJudgeOutput.model_validate_json(cached), item, response)
        last_error = "unknown error"
        for _ in range(self.retries + 1):
            try:
                self.calls += 1
                result = self.client.complete_json(self.rubric, self._prompt(item, response), JSON_SCHEMA)
                out = LLMJudgeOutput.model_validate(result.data)
            except ValidationError:
                last_error = "response did not match the rubric schema"
                continue
            except LLMError as exc:
                last_error = str(exc)
                self._consecutive_failures += 1
                if self._consecutive_failures >= self.max_consecutive_failures:
                    self.disabled_reason = last_error
                break
            self._consecutive_failures = 0
            if self.cache is not None:
                self.cache.put(key, self.rubric_version, item.id, a_hash, out.model_dump_json())
            return self._to_judgment(out, item, response)
        return self._fallback(item, response, last_error)
