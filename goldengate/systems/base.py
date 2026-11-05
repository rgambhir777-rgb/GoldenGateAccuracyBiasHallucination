"""The pluggable interface every system under test implements."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from typing import Any

from goldengate.core.models import ReleaseInfo, Response

ABSTAIN_TEXT = (
    "I don't have information about that in Meridian Bank's policy documents, "
    "so I can't answer it reliably."
)


def stable_hash(*parts: Any, length: int = 12) -> str:
    """Deterministic short SHA-256 hash of JSON-serialisable parts."""
    payload = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


class RAGSystem(ABC):
    """A retrieval-augmented question answering system under evaluation.

    Implementations must be safe to call repeatedly and should never raise for
    a single bad question: failures are returned as a :class:`Response` with
    ``error`` set so the run continues and the item is scored as a failure.
    """

    name: str = "system"

    @abstractmethod
    def answer(self, question: str, user_context: dict[str, Any] | None = None) -> Response:
        """Answer ``question`` for a user described by ``user_context``."""

    @abstractmethod
    def release_info(self) -> ReleaseInfo:
        """Metadata that identifies this release (model, prompt hash, retriever)."""
