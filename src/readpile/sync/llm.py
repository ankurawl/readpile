"""LLM client — thin wrapper around the OpenAI-compatible API."""

from __future__ import annotations

import os
import time
import logging

log = logging.getLogger("readpile.sync")

_TRANSIENT_STATUS_CODES = {429, 500, 502, 503}
_MAX_RETRIES = 3
_BACKOFF_SECONDS = [1, 2, 4]

_PROVIDER_BASE_URLS: dict[str, str] = {
    "claude": "https://api.anthropic.com/v1",
    "openai": "",
    "ollama": "http://localhost:11434/v1",
}


def generate(system_prompt: str, user_prompt: str, config: dict) -> str:
    """Call an LLM via the OpenAI-compatible API and return the response text.

    Supports claude, openai, and ollama providers.  Retries transient errors
    with exponential backoff (3 attempts, 1s / 2s / 4s).
    """
    from openai import OpenAI, APIStatusError

    llm_cfg = config.get("llm", {})
    provider = llm_cfg.get("provider", "claude")
    model = llm_cfg.get("model", "claude-sonnet-4-6")

    api_key = os.environ.get("READPILE_LLM_API_KEY") or llm_cfg.get("api_key", "")
    if not api_key and provider != "ollama":
        raise RuntimeError(
            f"READPILE_LLM_API_KEY environment variable is required for provider '{provider}'"
        )

    base_url = llm_cfg.get("base_url") or _PROVIDER_BASE_URLS.get(provider, "")

    client_kwargs: dict = {"api_key": api_key or "ollama"}
    if base_url:
        client_kwargs["base_url"] = base_url

    client = OpenAI(**client_kwargs)

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return response.choices[0].message.content or ""
        except APIStatusError as exc:
            if exc.status_code in _TRANSIENT_STATUS_CODES:
                last_exc = exc
                delay = _BACKOFF_SECONDS[attempt] if attempt < len(_BACKOFF_SECONDS) else _BACKOFF_SECONDS[-1]
                log.warning("LLM API returned %d, retrying in %ds (attempt %d/%d)", exc.status_code, delay, attempt + 1, _MAX_RETRIES)
                time.sleep(delay)
                continue
            raise
        except Exception as exc:
            last_exc = exc
            delay = _BACKOFF_SECONDS[attempt] if attempt < len(_BACKOFF_SECONDS) else _BACKOFF_SECONDS[-1]
            log.warning("LLM API error: %s, retrying in %ds (attempt %d/%d)", exc, delay, attempt + 1, _MAX_RETRIES)
            time.sleep(delay)

    raise last_exc  # type: ignore[misc]
