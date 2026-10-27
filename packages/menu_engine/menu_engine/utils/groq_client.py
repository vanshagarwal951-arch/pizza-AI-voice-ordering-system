"""Groq API client — uses OpenAI SDK to avoid Cloudflare 1010 (urllib User-Agent block)."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

# Groq retired llama-3.3-70b-versatile on 2026-08-16; see console.groq.com/docs/models
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
# Fastest Groq model with tool calling (~1000 tok/s) — free tier voice default
DEFAULT_GROQ_VOICE_MODEL = "openai/gpt-oss-20b"
DEFAULT_GROQ_JUDGE_MODEL = "openai/gpt-oss-20b"


def get_groq_model() -> str:
    return os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip()


def get_groq_voice_model() -> str:
    """Smaller/faster model for real-time voice (tool calling supported)."""
    voice = os.getenv("GROQ_VOICE_MODEL", "").strip()
    if voice:
        return voice
    return DEFAULT_GROQ_VOICE_MODEL


def get_groq_judge_model() -> str:
    return os.getenv("GROQ_JUDGE_MODEL", DEFAULT_GROQ_JUDGE_MODEL).strip()


def groq_chat_completion(
    *,
    model: str,
    messages: list[dict[str, Any]],
    api_key: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.4,
    response_format: dict[str, str] | None = None,
    timeout: float = 30,
    max_retries: int = 2,
) -> dict[str, Any]:
    from openai import (
        APIConnectionError,
        APITimeoutError,
        InternalServerError,
        OpenAI,
        RateLimitError,
    )

    key = (api_key or os.getenv("GROQ_API_KEY", "")).strip()
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set")

    client = OpenAI(
        api_key=key,
        base_url="https://api.groq.com/openai/v1",
        timeout=timeout,
    )

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    if response_format:
        kwargs["response_format"] = response_format

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(**kwargs)
            return response.model_dump()
        except (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError) as exc:
            last_exc = exc
            if attempt < max_retries:
                delay = 0.5 * (2 ** attempt)
                logger.warning(
                    "Groq API transient error on attempt %d/%d (%s). Retrying in %.1fs...",
                    attempt + 1,
                    max_retries + 1,
                    exc,
                    delay,
                )
                time.sleep(delay)
            else:
                logger.error("Groq API failed after %d retries: %s", max_retries, exc)
                raise

    if last_exc:
        raise last_exc
    raise RuntimeError("Groq completion failed with unknown error")
