from unittest.mock import patch, MagicMock
import pytest
from mediakit.summarizer.providers import (
    OllamaProvider, ClaudeProvider, OpenAIProvider, CustomProvider,
    get_provider, LLMConnectionError, LLMModelNotFoundError,
)


def test_ollama_provider_generate():
    mock_ollama = MagicMock()
    mock_response = MagicMock()
    mock_response.message.content = "Generated text"
    mock_ollama.chat.return_value = mock_response

    with patch.dict("sys.modules", {"ollama": mock_ollama}):
        provider = OllamaProvider(model="llama3.2")
        result = provider.generate("test prompt")
        assert result == "Generated text"
        mock_ollama.chat.assert_called_once()


def test_ollama_model_not_found():
    mock_ollama = MagicMock()
    mock_ollama.ResponseError = type("ResponseError", (Exception,), {})
    mock_ollama.chat.side_effect = mock_ollama.ResponseError("model not found")

    with patch.dict("sys.modules", {"ollama": mock_ollama}):
        provider = OllamaProvider()
        with pytest.raises((LLMConnectionError, LLMModelNotFoundError)):
            provider.generate("test")


def test_get_provider_ollama():
    config = {"summarize": {"provider": "ollama", "ollama": {"model": "llama3.2", "host": "http://localhost:11434"}}}
    provider = get_provider(config)
    assert isinstance(provider, OllamaProvider)


def test_get_provider_claude():
    config = {"summarize": {"provider": "claude", "claude": {"model": "claude-sonnet-4-20250514", "api_key": "test-key"}}}
    provider = get_provider(config)
    assert isinstance(provider, ClaudeProvider)


def test_get_provider_openai():
    config = {"summarize": {"provider": "openai", "openai": {"model": "gpt-4o", "api_key": "test-key"}}}
    provider = get_provider(config)
    assert isinstance(provider, OpenAIProvider)


def test_get_provider_auto_fallback():
    config = {"summarize": {"provider": "auto", "ollama": {"model": "llama3.2", "host": "http://localhost:11434"}}}
    with patch.dict("os.environ", {}, clear=False):
        # Remove API keys if set
        import os
        env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")}
        with patch.dict("os.environ", env, clear=True):
            provider = get_provider(config)
            assert isinstance(provider, OllamaProvider)
