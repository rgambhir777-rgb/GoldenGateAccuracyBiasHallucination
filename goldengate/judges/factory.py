"""Choose the judge for a run: offline, LLM, or LLM with offline fallback."""

from __future__ import annotations

from collections.abc import Mapping

from goldengate.config import Settings
from goldengate.core.models import Chunk
from goldengate.judges.llm import LLMJudge
from goldengate.judges.offline import OfflineJudge
from goldengate.llm.client import LLMClient, LLMError
from goldengate.releases.db import SqlJudgeCache


def build_judge(mode: str, settings: Settings, chunks: Mapping[str, Chunk]) -> tuple[OfflineJudge | LLMJudge, list[str]]:
    """Return the judge and any warnings to surface to the user.

    * ``offline`` - always the offline judge.
    * ``auto`` - LLM judge when an API key is configured, otherwise offline.
    * ``llm`` - LLM judge; falls back to offline (with a warning) without a usable key.
    """
    if mode == "offline":
        return OfflineJudge(chunks), []
    if settings.llm_provider is None:
        warnings = ["LLM judge requested but no API key is configured; using the offline judge."] \
            if mode == "llm" else []
        return OfflineJudge(chunks), warnings
    try:
        client = LLMClient(settings)
    except LLMError as exc:
        return OfflineJudge(chunks), [f"LLM judge unavailable ({exc}); using the offline judge."]
    return LLMJudge(client, chunks, cache=SqlJudgeCache()), []
