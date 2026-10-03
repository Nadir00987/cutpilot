"""CutPilot AI — LLM client (pluggable, OpenAI-compatible).

Environment:
    LLM_API_URL   Base URL of an OpenAI-compatible chat endpoint
                  (e.g. https://api.openai.com/v1)
    LLM_API_KEY   Bearer key
    LLM_MODEL     Model name (e.g. gpt-4o-mini)

Every caller MUST catch :class:`LLMNotConfigured` and fall back to rules.
"""

from __future__ import annotations

import os

import httpx


class LLMNotConfigured(RuntimeError):
    """Raised when no LLM endpoint is configured."""


def llm_available() -> bool:
    return bool(os.environ.get("LLM_API_URL") and os.environ.get("LLM_API_KEY"))


def chat(messages: list[dict], json_mode: bool = False, timeout: int = 60) -> str:
    """POST to {LLM_API_URL}/chat/completions.

    Raises:
        LLMNotConfigured: if LLM_API_URL / LLM_API_KEY are not set.
        RuntimeError: on non-2xx responses.
    """
    base = os.environ.get("LLM_API_URL", "").rstrip("/")
    key = os.environ.get("LLM_API_KEY", "")
    if not base or not key:
        raise LLMNotConfigured("LLM_API_URL / LLM_API_KEY not set")

    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    payload: dict = {"model": model, "messages": messages}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
        )
    if resp.status_code >= 400:
        raise RuntimeError(f"LLM HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    return data["choices"][0]["message"]["content"]
