"""RAG pipeline that uses the offline retriever plus a real LLM (Anthropic or OpenAI-compatible)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from goldengate.config import Settings
from goldengate.core.models import ReleaseInfo, Response, TokenUsage
from goldengate.core.text import extract_citations
from goldengate.llm.client import LLMClient, LLMError
from goldengate.retrieval.corpus import cached_corpus
from goldengate.retrieval.retrievers import build_retriever
from goldengate.systems.base import RAGSystem, stable_hash

PROMPT_FILE = Path(__file__).parent / "prompts" / "rag_v1.md"

ANSWER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["answer", "citations"],
    "properties": {"answer": {"type": "string"}, "citations": {"type": "array", "items": {"type": "string"}}},
}


class LLMRAGSystem(RAGSystem):
    """Retrieve with BM25/TF-IDF, then ask an LLM to answer with citations using ``rag_v1``."""

    def __init__(self, settings: Settings, release_id: str = "llm_rag", top_k: int | None = None) -> None:
        self.settings = settings
        self.release_id = release_id
        self.name = release_id
        self.top_k = top_k or settings.top_k
        self.retriever = build_retriever(settings.retriever, cached_corpus())
        raw = PROMPT_FILE.read_text(encoding="utf-8")
        first, _, body = raw.partition("\n")
        self.prompt_version = first.split(":", 1)[1].strip() if first.startswith("prompt_version:") else "rag"
        self.template = body
        model = settings.rag_model if settings.llm_provider == "anthropic" else settings.openai_model
        self.client = LLMClient(settings, model=model)

    def release_info(self) -> ReleaseInfo:
        return ReleaseInfo(
            release_id=self.release_id, version=self.prompt_version, system="llm",
            description=f"LLM RAG ({self.client.provider}) with prompt {self.prompt_version}",
            model=self.client.model, prompt_hash=stable_hash(self.template),
            retriever_config={**self.retriever.config(), "top_k": self.top_k},
        )

    def answer(self, question: str, user_context: dict[str, Any] | None = None) -> Response:
        started = time.perf_counter()
        retrieved = self.retriever.search(question, self.top_k)
        passages = "\n".join(f"[{c.chunk_id}] {c.text}" for c in retrieved) or "(no passages found)"
        prompt = self.template.replace("{passages}", passages).replace("{question}", question)
        try:
            result = self.client.complete_json("You answer bank policy questions with citations.", prompt,
                                               ANSWER_SCHEMA, max_tokens=1500)
        except LLMError as exc:
            return Response(answer="", retrieved=retrieved, error=str(exc),
                            latency_ms=round((time.perf_counter() - started) * 1000, 1))
        answer = str(result.data.get("answer", ""))
        citations = [str(c) for c in result.data.get("citations", [])] or extract_citations(answer)
        return Response(
            answer=answer, citations=citations, retrieved=retrieved,
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            usage=TokenUsage(prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens),
        )
