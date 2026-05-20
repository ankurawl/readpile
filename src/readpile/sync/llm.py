"""LLM client — thin wrapper around the OpenAI-compatible API.

Any provider with an OpenAI-compatible chat completions endpoint works.
Configure ``base_url`` and ``model`` in ``[llm]``; set ``api_key`` via
the ``READPILE_LLM_API_KEY`` env var or in the config.
"""

from __future__ import annotations

import os
import time
import logging

log = logging.getLogger("readpile.sync")

_TRANSIENT_STATUS_CODES = {429, 500, 502, 503}
_MAX_RETRIES = 3
_BACKOFF_SECONDS = [1, 2, 4]

_BASE_URL_SHORTCUTS: dict[str, str] = {
    "anthropic": "https://api.anthropic.com/v1",
    "ollama": "http://localhost:11434/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
}


def _is_local_url(url: str) -> bool:
    return url.startswith("http://localhost") or url.startswith("http://127.0.0.1")


def generate(system_prompt: str, user_prompt: str, config: dict) -> str:
    """Call an LLM via the OpenAI-compatible API and return the response text.

    Works with any provider that exposes an OpenAI-compatible endpoint.
    Retries transient errors with exponential backoff (3 attempts, 1s / 2s / 4s).
    """
    from openai import OpenAI, APIStatusError

    llm_cfg = config.get("llm", {})
    model = llm_cfg.get("model", "claude-sonnet-4-6")
    base_url = llm_cfg.get("base_url", "")

    if base_url in _BASE_URL_SHORTCUTS:
        base_url = _BASE_URL_SHORTCUTS[base_url]

    api_key = os.environ.get("READPILE_LLM_API_KEY") or llm_cfg.get("api_key", "")
    if not api_key and not _is_local_url(base_url):
        raise RuntimeError(
            "READPILE_LLM_API_KEY environment variable is required "
            "(or set api_key in [llm] config)"
        )

    client_kwargs: dict = {"api_key": api_key or "not-needed"}
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
