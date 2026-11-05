"""Runtime settings loaded from environment variables and the local ``.env`` file.

Process environment variables win over values stored in ``.env`` so CI secrets
always take precedence over a developer's local file.
"""

from __future__ import annotations

import os
from typing import Literal

from dotenv import dotenv_values
from pydantic import BaseModel, Field

from goldengate import paths

JudgeMode = Literal["auto", "offline", "llm"]
RetrieverKind = Literal["bm25", "tfidf"]

# Keys that may be stored in .env through the Settings page.
EDITABLE_KEYS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "GOLDENGATE_JUDGE_MODE",
    "GOLDENGATE_JUDGE_MODEL",
    "GOLDENGATE_RAG_MODEL",
    "GOLDENGATE_OPENAI_MODEL",
    "GOLDENGATE_RETRIEVER",
    "GOLDENGATE_TOP_K",
    "GOLDENGATE_BOOTSTRAP_SAMPLES",
)
SECRET_KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")


class Settings(BaseModel):
    """Effective configuration for one process."""

    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    judge_mode: JudgeMode = "auto"
    judge_model: str = "claude-sonnet-5-5"
    rag_model: str = "claude-opus-5-5"
    openai_model: str = "gpt-4o-mini"
    retriever: RetrieverKind = "bm25"
    top_k: int = Field(default=5, ge=1, le=20)
    bootstrap_samples: int = Field(default=1000, ge=100, le=20000)
    seed: int = 7

    @property
    def llm_provider(self) -> Literal["anthropic", "openai"] | None:
        """Which LLM provider is configured, preferring Anthropic."""
        if self.anthropic_api_key:
            return "anthropic"
        if self.openai_api_key:
            return "openai"
        return None


def _raw_values() -> dict[str, str]:
    values: dict[str, str] = {}
    env_path = paths.env_file()
    if env_path.exists():
        values.update({k: v for k, v in dotenv_values(env_path).items() if v is not None})
    for key in EDITABLE_KEYS + ("GOLDENGATE_SEED",):
        if os.environ.get(key):
            values[key] = os.environ[key]
    return {k: v for k, v in values.items() if v != ""}


def load_settings() -> Settings:
    """Build settings, ignoring malformed values instead of crashing."""
    raw = _raw_values()
    data: dict[str, object] = {
        "anthropic_api_key": raw.get("ANTHROPIC_API_KEY"),
        "openai_api_key": raw.get("OPENAI_API_KEY"),
    }
    mapping = {
        "OPENAI_BASE_URL": "openai_base_url",
        "GOLDENGATE_JUDGE_MODE": "judge_mode",
        "GOLDENGATE_JUDGE_MODEL": "judge_model",
        "GOLDENGATE_RAG_MODEL": "rag_model",
        "GOLDENGATE_OPENAI_MODEL": "openai_model",
        "GOLDENGATE_RETRIEVER": "retriever",
        "GOLDENGATE_TOP_K": "top_k",
        "GOLDENGATE_BOOTSTRAP_SAMPLES": "bootstrap_samples",
        "GOLDENGATE_SEED": "seed",
    }
    for env_key, field in mapping.items():
        if env_key in raw:
            data[field] = raw[env_key]
    try:
        return Settings.model_validate(data)
    except ValueError:
        safe = {k: v for k, v in data.items() if k in ("anthropic_api_key", "openai_api_key")}
        return Settings.model_validate(safe)


def mask_secret(value: str | None) -> str | None:
    """Mask a secret for display, keeping only the last four characters."""
    if not value:
        return None
    return ("*" * 8) + value[-4:] if len(value) > 4 else "*" * len(value)


def save_env_values(updates: dict[str, str | None]) -> None:
    """Persist values to ``.env``; ``None`` or empty string removes a key."""
    env_path = paths.env_file()
    current: dict[str, str] = {}
    if env_path.exists():
        current = {k: v for k, v in dotenv_values(env_path).items() if v is not None}
    for key, value in updates.items():
        if key not in EDITABLE_KEYS:
            raise ValueError(f"Setting {key} cannot be edited")
        if value is None or value == "":
            current.pop(key, None)
        else:
            current[key] = value.replace("\n", "").strip()
    lines = ["# GoldenGate local settings (written by the dashboard). Do not commit."]
    lines += [f"{k}={v}" for k, v in sorted(current.items())]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
