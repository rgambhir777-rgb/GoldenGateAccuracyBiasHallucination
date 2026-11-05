"""Adapters for evaluating external RAG systems: a generic HTTP endpoint and JSONL replay."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx
import yaml
from pydantic import BaseModel, Field

from goldengate.core.models import ReleaseInfo, Response, RetrievedChunk, TokenUsage
from goldengate.systems.base import RAGSystem, stable_hash


def json_path(data: Any, path: str | None) -> Any:
    """Tiny JSON path: ``a.b.0.c`` and ``items[*].id`` (``[*]`` maps over a list)."""
    if not path:
        return None
    parts = [p for p in path.replace("[*]", ".*").replace("[", ".").replace("]", "").split(".") if p]
    return _walk(data, parts)


def _walk(current: Any, parts: list[str]) -> Any:
    if not parts:
        return current
    head, rest = parts[0], parts[1:]
    if head == "*":
        return [_walk(x, rest) for x in current] if isinstance(current, list) else None
    if isinstance(current, list):
        try:
            current = current[int(head)]
        except (ValueError, IndexError):
            return None
    elif isinstance(current, dict):
        current = current.get(head)
    else:
        return None
    return None if current is None else _walk(current, rest)


class HTTPAdapterConfig(BaseModel):
    """YAML/JSON config for :class:`HTTPRAGSystem`."""

    release_id: str
    url: str
    method: str = "POST"
    headers: dict[str, str] = Field(default_factory=dict)
    request_template: dict[str, Any] = Field(
        default_factory=lambda: {"question": "{question}", "user_context": "{user_context}"})
    answer_path: str = "answer"
    citations_path: str | None = "citations"
    chunks_path: str | None = "retrieved"
    chunk_id_field: str = "id"
    chunk_text_field: str = "text"
    chunk_score_field: str = "score"
    prompt_tokens_path: str | None = None
    completion_tokens_path: str | None = None
    model: str = "external"
    version: str = "external"
    timeout_s: float = 30.0


def _fill(template: Any, question: str, user_context: dict[str, Any]) -> Any:
    if isinstance(template, dict):
        return {k: _fill(v, question, user_context) for k, v in template.items()}
    if isinstance(template, list):
        return [_fill(v, question, user_context) for v in template]
    if template == "{user_context}":
        return user_context
    if isinstance(template, str):
        return template.replace("{question}", question)
    return template


class HTTPRAGSystem(RAGSystem):
    """Call any RAG service over HTTP and map its JSON response with configurable paths."""

    def __init__(self, config: HTTPAdapterConfig, client: httpx.Client | None = None) -> None:
        self.config = config
        self.name = config.release_id
        self.client = client or httpx.Client(timeout=config.timeout_s)

    @classmethod
    def from_file(cls, path: Path) -> HTTPRAGSystem:
        return cls(HTTPAdapterConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8"))))

    def release_info(self) -> ReleaseInfo:
        cfg = self.config
        return ReleaseInfo(release_id=cfg.release_id, version=cfg.version, system="http", model=cfg.model,
                           description=f"External RAG service at {cfg.url}",
                           prompt_hash=stable_hash(cfg.request_template, cfg.url),
                           retriever_config={"external": True})

    def answer(self, question: str, user_context: dict[str, Any] | None = None) -> Response:
        cfg = self.config
        started = time.perf_counter()
        body = _fill(cfg.request_template, question, user_context or {})
        try:
            resp = self.client.request(cfg.method, cfg.url, json=body, headers=cfg.headers)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            return Response(answer="", error=f"HTTP adapter error: {exc.__class__.__name__}",
                            latency_ms=round((time.perf_counter() - started) * 1000, 1))
        chunks_raw = json_path(data, cfg.chunks_path) or []
        retrieved = [
            RetrievedChunk(chunk_id=str(c.get(cfg.chunk_id_field, "")), text=str(c.get(cfg.chunk_text_field, "")),
                           score=float(c.get(cfg.chunk_score_field, 0) or 0), rank=i + 1)
            for i, c in enumerate(chunks_raw) if isinstance(c, dict)
        ]
        citations = json_path(data, cfg.citations_path) or []
        return Response(
            answer=str(json_path(data, cfg.answer_path) or ""),
            citations=[str(c) for c in citations] if isinstance(citations, list) else [],
            retrieved=retrieved, latency_ms=round((time.perf_counter() - started) * 1000, 1),
            usage=TokenUsage(prompt_tokens=int(json_path(data, cfg.prompt_tokens_path) or 0),
                             completion_tokens=int(json_path(data, cfg.completion_tokens_path) or 0)),
        )


class ReplayRecord(BaseModel):
    """One recorded answer. Matched to golden items by ``item_id`` or exact ``question``."""

    item_id: str | None = None
    question: str | None = None
    answer: str
    citations: list[str] = Field(default_factory=list)
    retrieved: list[RetrievedChunk] = Field(default_factory=list)
    latency_ms: float = 0.0
    usage: TokenUsage = Field(default_factory=TokenUsage)


class ReplaySystem(RAGSystem):
    """Evaluate recorded outputs from a JSONL file without calling any system."""

    def __init__(self, path: Path, release_id: str | None = None, items_by_question: dict[str, str] | None = None):
        self.path = path
        self.name = release_id or path.stem
        self.records = [ReplayRecord.model_validate_json(line)
                        for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self._by_question = {r.question: r for r in self.records if r.question}
        self._by_item = {r.item_id: r for r in self.records if r.item_id}
        self.items_by_question = items_by_question or {}

    def release_info(self) -> ReleaseInfo:
        return ReleaseInfo(release_id=self.name, version="replay", system="replay", model="recorded",
                           description=f"Replay of recorded outputs from {self.path.name}",
                           prompt_hash=stable_hash(self.path.read_text(encoding="utf-8")),
                           retriever_config={"replay": True})

    def answer(self, question: str, user_context: dict[str, Any] | None = None) -> Response:
        record = self._by_question.get(question)
        if record is None and question in self.items_by_question:
            record = self._by_item.get(self.items_by_question[question])
        if record is None:
            return Response(answer="", error="no recorded answer for this question")
        return Response(answer=record.answer, citations=record.citations, retrieved=record.retrieved,
                        latency_ms=record.latency_ms, usage=record.usage)
