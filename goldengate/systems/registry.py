"""Resolve a ``--system`` string into a :class:`RAGSystem`.

Accepted forms:

* ``release_1.0`` ... ``release_1.3`` - offline demo releases
* ``llm`` or ``llm:<release_id>`` - LLM RAG pipeline (needs an API key)
* ``http:<config.yaml>`` - external HTTP service
* ``replay:<outputs.jsonl>`` - recorded answers
"""

from __future__ import annotations

from pathlib import Path

from goldengate.config import Settings
from goldengate.core.models import GoldenItem
from goldengate.systems.adapters import HTTPRAGSystem, ReplaySystem
from goldengate.systems.base import RAGSystem
from goldengate.systems.demo import DEMO_RELEASES, demo_system
from goldengate.systems.llm_rag import LLMRAGSystem


class SystemSpecError(ValueError):
    """Raised when a system specification is invalid or unavailable."""


def available_systems(settings: Settings) -> list[dict[str, object]]:
    """Systems the dashboard can start runs for."""
    systems: list[dict[str, object]] = [
        {"id": cfg.release_id, "label": f"Demo {cfg.release_id}", "description": cfg.description,
         "available": True} for cfg in DEMO_RELEASES.values()
    ]
    systems.append({"id": "llm", "label": "LLM RAG (rag-v1 prompt)",
                    "description": "Same retriever + Anthropic or OpenAI-compatible model.",
                    "available": settings.llm_provider is not None,
                    "reason": None if settings.llm_provider else "Set ANTHROPIC_API_KEY or OPENAI_API_KEY"})
    return systems


def build_system(spec: str, settings: Settings, items: list[GoldenItem] | None = None,
                 release_id: str | None = None) -> RAGSystem:
    """Create the system named by ``spec`` (see module docstring)."""
    if spec in DEMO_RELEASES:
        return demo_system(spec, retriever=settings.retriever, top_k=settings.top_k, seed=settings.seed)
    kind, _, arg = spec.partition(":")
    if kind == "llm":
        if settings.llm_provider is None:
            raise SystemSpecError("The LLM system needs ANTHROPIC_API_KEY or OPENAI_API_KEY (see .env.example)")
        return LLMRAGSystem(settings, release_id=release_id or arg or "llm_rag")
    if kind == "http":
        path = Path(arg)
        if not path.exists():
            raise SystemSpecError(f"HTTP adapter config '{arg}' not found")
        system = HTTPRAGSystem.from_file(path)
        if release_id:
            system.config.release_id = release_id
            system.name = release_id
        return system
    if kind == "replay":
        path = Path(arg)
        if not path.exists():
            raise SystemSpecError(f"Replay file '{arg}' not found")
        mapping = {i.question: i.id for i in items or []}
        return ReplaySystem(path, release_id=release_id, items_by_question=mapping)
    raise SystemSpecError(f"Unknown system '{spec}'. Use one of {sorted(DEMO_RELEASES)}, llm, http:<cfg>, replay:<file>")
