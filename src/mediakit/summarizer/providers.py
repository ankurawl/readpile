"""LLM providers — adapters for Ollama, Claude, OpenAI, etc."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LLMConnectionError(Exception):
    """Raised when a connection to the LLM backend fails."""


class LLMModelNotFoundError(Exception):
    """Raised when the requested model is not available."""


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class LLMProvider(ABC):
    """Strategy interface for LLM text generation."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Send *prompt* to the model and return the generated text."""
        ...


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------


class OllamaProvider(LLMProvider):
    """Local inference via `Ollama <https://ollama.com>`_."""

    def __init__(self, model: str = "llama3.2", host: str = "http://localhost:11434") -> None:
        self.model = model
        self.host = host

    @staticmethod
    def _check_deps() -> None:
        try:
            import ollama  # noqa: F401
        except ImportError:
            raise SystemExit(
                "Ollama provider requires the ollama package. Install with:\n"
                "  pip install ollama\n"
            )

    def generate(self, prompt: str) -> str:
        self._check_deps()
        import ollama  # lazily imported — not every user will have it

        try:
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            )
        except ollama.ResponseError as exc:
            if "not found" in str(exc).lower():
                raise LLMModelNotFoundError(
                    f"Model '{self.model}' not found. Pull it with `ollama pull {self.model}`"
                ) from exc
            raise LLMConnectionError(f"Ollama error: {exc}") from exc
        except Exception as exc:
            msg = str(exc).lower()
            if "connect" in msg or "refused" in msg:
                raise LLMConnectionError(
                    "Ollama is not running. Start it with `ollama serve`"
                ) from exc
            raise LLMConnectionError(f"Ollama error: {exc}") from exc

        return response.message.content


# ---------------------------------------------------------------------------
# Claude (Anthropic)
# ---------------------------------------------------------------------------


class ClaudeProvider(LLMProvider):
    """Anthropic Messages API."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")

    @staticmethod
    def _check_deps() -> None:
        try:
            import anthropic  # noqa: F401
        except ImportError:
            raise SystemExit(
                "Claude provider requires the anthropic package. Install with:\n"
                "  pip install 'mediakit[claude]'\n"
                "  or: pip install anthropic\n"
            )

    def generate(self, prompt: str) -> str:
        self._check_deps()
        import anthropic  # optional dependency

        try:
            client = anthropic.Anthropic(api_key=self.api_key)
            response = client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.AuthenticationError as exc:
            raise LLMConnectionError(
                "Invalid or missing ANTHROPIC_API_KEY. "
                "Set it via env var or config."
            ) from exc
        except anthropic.NotFoundError as exc:
            raise LLMModelNotFoundError(
                f"Model '{self.model}' not found on Anthropic."
            ) from exc
        except Exception as exc:
            raise LLMConnectionError(f"Claude API error: {exc}") from exc

        return response.content[0].text


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------


class OpenAIProvider(LLMProvider):
    """OpenAI Chat Completions API."""

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")

    @staticmethod
    def _check_deps() -> None:
        try:
            import openai  # noqa: F401
        except ImportError:
            raise SystemExit(
                "OpenAI provider requires the openai package. Install with:\n"
                "  pip install 'mediakit[openai]'\n"
                "  or: pip install openai\n"
            )

    def generate(self, prompt: str) -> str:
        self._check_deps()
        import openai  # optional dependency

        try:
            client = openai.OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            )
        except openai.AuthenticationError as exc:
            raise LLMConnectionError(
                "Invalid or missing OPENAI_API_KEY. "
                "Set it via env var or config."
            ) from exc
        except openai.NotFoundError as exc:
            raise LLMModelNotFoundError(
                f"Model '{self.model}' not found on OpenAI."
            ) from exc
        except Exception as exc:
            raise LLMConnectionError(f"OpenAI API error: {exc}") from exc

        return response.choices[0].message.content


# ---------------------------------------------------------------------------
# Custom (OpenAI-compatible endpoint)
# ---------------------------------------------------------------------------


class CustomProvider(LLMProvider):
    """Any OpenAI-compatible API endpoint (vLLM, Together, Groq, etc.)."""

    def __init__(
        self,
        endpoint: str,
        model: str,
        api_key: str | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key

    def generate(self, prompt: str) -> str:
        import openai  # uses the OpenAI client pointed at a custom base_url

        try:
            client = openai.OpenAI(api_key=self.api_key or "unused", base_url=self.endpoint)
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            msg = str(exc).lower()
            if "connect" in msg or "refused" in msg:
                raise LLMConnectionError(
                    f"Cannot connect to custom endpoint at {self.endpoint}"
                ) from exc
            raise LLMConnectionError(f"Custom provider error: {exc}") from exc

        return response.choices[0].message.content


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_provider(config: dict) -> LLMProvider:
    """Instantiate the correct :class:`LLMProvider` from a mediakit config dict.

    The provider is determined by ``config["summarize"]["provider"]``.
    Special value ``"auto"`` probes environment variables to pick the best
    available backend.
    """
    summarize_cfg = config.get("summarize", {})
    provider_name = summarize_cfg.get("provider", "ollama").lower()

    # --- auto-detection --------------------------------------------------
    if provider_name == "auto":
        if os.environ.get("ANTHROPIC_API_KEY"):
            provider_name = "claude"
        elif os.environ.get("OPENAI_API_KEY"):
            provider_name = "openai"
        else:
            provider_name = "ollama"

    # --- dispatch --------------------------------------------------------
    if provider_name == "ollama":
        ollama_cfg = summarize_cfg.get("ollama", {})
        return OllamaProvider(
            model=ollama_cfg.get("model", "llama3.2"),
            host=ollama_cfg.get("host", "http://localhost:11434"),
        )

    if provider_name == "claude":
        claude_cfg = summarize_cfg.get("claude", {})
        return ClaudeProvider(
            model=claude_cfg.get("model", "claude-sonnet-4-20250514"),
            api_key=claude_cfg.get("api_key"),
        )

    if provider_name == "openai":
        openai_cfg = summarize_cfg.get("openai", {})
        return OpenAIProvider(
            model=openai_cfg.get("model", "gpt-4o"),
            api_key=openai_cfg.get("api_key"),
        )

    if provider_name == "custom":
        custom_cfg = summarize_cfg.get("custom", {})
        endpoint = custom_cfg.get("endpoint", "")
        if not endpoint:
            raise ValueError(
                "Custom provider requires an 'endpoint' in [summarize.custom] config."
            )
        return CustomProvider(
            endpoint=endpoint,
            model=custom_cfg.get("model", ""),
            api_key=custom_cfg.get("api_key"),
        )

    raise ValueError(f"Unknown LLM provider: {provider_name!r}")
