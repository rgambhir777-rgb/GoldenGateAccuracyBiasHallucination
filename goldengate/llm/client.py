"""Minimal JSON-output LLM client for Anthropic (official SDK) or OpenAI-compatible APIs.

Determinism: current Claude models do not accept sampling parameters such as
``temperature`` (the API rejects them), so for Anthropic determinism comes from
structured JSON output plus result caching. OpenAI-compatible providers are
called with ``temperature=0``.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import anthropic
import httpx

from goldengate.config import Settings


class LLMError(RuntimeError):
    """Raised for any provider failure; callers fall back to offline behaviour."""


@dataclass
class LLMResult:
    data: dict[str, Any]
    model: str
    prompt_tokens: int
    completion_tokens: int


class LLMClient:
    """Calls the configured provider and returns validated JSON objects."""

    def __init__(self, settings: Settings, model: str | None = None, max_retries: int = 2,
                 timeout: float = 60.0) -> None:
        self.provider = settings.llm_provider
        if self.provider is None:
            raise LLMError("No ANTHROPIC_API_KEY or OPENAI_API_KEY configured")
        self.settings = settings
        self.max_retries = max_retries
        self.timeout = timeout
        if self.provider == "anthropic":
            self.model = model or settings.judge_model
            self._anthropic = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=max_retries,
                                                  timeout=timeout)
        else:
            self.model = model or settings.openai_model

    def complete_json(self, system: str, user: str, schema: dict[str, Any], max_tokens: int = 4000) -> LLMResult:
        """Return a JSON object matching ``schema`` or raise :class:`LLMError`."""
        if self.provider == "anthropic":
            return self._anthropic_json(system, user, schema, max_tokens)
        return self._openai_json(system, user, schema, max_tokens)

    def _anthropic_json(self, system: str, user: str, schema: dict[str, Any], max_tokens: int) -> LLMResult:
        try:
            response = self._anthropic.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            )
        except anthropic.AuthenticationError as exc:
            raise LLMError("Anthropic rejected the API key (401)") from exc
        except anthropic.PermissionDeniedError as exc:
            raise LLMError("Anthropic API key lacks permission for this model") from exc
        except anthropic.NotFoundError as exc:
            raise LLMError(f"Model '{self.model}' not found") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("Anthropic rate limit reached") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Anthropic API error {exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Could not reach the Anthropic API") from exc
        if response.stop_reason == "refusal":
            raise LLMError("The model declined to answer this request")
        text = next((b.text for b in response.content if b.type == "text"), "")
        return LLMResult(data=_parse_json(text), model=response.model,
                         prompt_tokens=response.usage.input_tokens, completion_tokens=response.usage.output_tokens)

    def _openai_json(self, system: str, user: str, schema: dict[str, Any], max_tokens: int) -> LLMResult:
        url = self.settings.openai_base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "result", "schema": schema, "strict": False}},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        headers = {"Authorization": f"Bearer {self.settings.openai_api_key}"}
        last_error = "unknown error"
        for attempt in range(self.max_retries + 1):
            try:
                resp = httpx.post(url, json=payload, headers=headers, timeout=self.timeout)
            except httpx.HTTPError as exc:
                last_error = f"connection error: {exc.__class__.__name__}"
            else:
                if resp.status_code in (401, 403):
                    raise LLMError("OpenAI-compatible API rejected the API key")
                if resp.status_code == 200:
                    body = resp.json()
                    text = body["choices"][0]["message"]["content"] or ""
                    usage = body.get("usage", {})
                    return LLMResult(data=_parse_json(text), model=body.get("model", self.model),
                                     prompt_tokens=usage.get("prompt_tokens", 0),
                                     completion_tokens=usage.get("completion_tokens", 0))
                last_error = f"HTTP {resp.status_code}"
                if resp.status_code < 500 and resp.status_code != 429:
                    break
            time.sleep(min(2**attempt, 8))
        raise LLMError(f"OpenAI-compatible API failed: {last_error}")


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError("Model did not return valid JSON") from exc
    if not isinstance(data, dict):
        raise LLMError("Model returned JSON that is not an object")
    return data
