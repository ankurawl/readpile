"""Tests for readpile.sync.llm — LLM client wrapper with retry logic."""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


# --- Base URL routing ---


class TestBaseURLRouting:
    @patch.dict("os.environ", {"READPILE_LLM_API_KEY": "test-key"}, clear=True)
    @patch("openai.OpenAI")
    def test_anthropic_shortcut(self, mock_openai_cls):
        from readpile.sync.llm import generate

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="response"))]
        )

        config = {"llm": {"base_url": "anthropic", "model": "claude-sonnet-4-6"}}
        result = generate("system", "user", config)

        mock_openai_cls.assert_called_once()
        call_kwargs = mock_openai_cls.call_args[1]
        assert call_kwargs["base_url"] == "https://api.anthropic.com/v1"
        assert call_kwargs["api_key"] == "test-key"
        assert result == "response"

    @patch.dict("os.environ", {"READPILE_LLM_API_KEY": "sk-openai"}, clear=True)
    @patch("openai.OpenAI")
    def test_no_base_url_uses_openai_default(self, mock_openai_cls):
        from readpile.sync.llm import generate

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="ok"))]
        )

        config = {"llm": {"model": "gpt-4o"}}
        generate("system", "user", config)

        call_kwargs = mock_openai_cls.call_args[1]
        assert "base_url" not in call_kwargs
        assert call_kwargs["api_key"] == "sk-openai"

    @patch.dict("os.environ", {}, clear=True)
    @patch("openai.OpenAI")
    def test_ollama_shortcut(self, mock_openai_cls):
        from readpile.sync.llm import generate

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="local"))]
        )

        config = {"llm": {"base_url": "ollama", "model": "llama3"}}
        generate("system", "user", config)

        call_kwargs = mock_openai_cls.call_args[1]
        assert call_kwargs["base_url"] == "http://localhost:11434/v1"
        assert call_kwargs["api_key"] == "not-needed"

    @patch.dict("os.environ", {"READPILE_LLM_API_KEY": "rtr-key"}, clear=True)
    @patch("openai.OpenAI")
    def test_openrouter_shortcut(self, mock_openai_cls):
        from readpile.sync.llm import generate

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="ok"))]
        )

        config = {"llm": {"base_url": "openrouter", "model": "google/gemini-2.0-flash"}}
        generate("system", "user", config)

        call_kwargs = mock_openai_cls.call_args[1]
        assert call_kwargs["base_url"] == "https://openrouter.ai/api/v1"

    @patch.dict("os.environ", {"READPILE_LLM_API_KEY": "gem-key"}, clear=True)
    @patch("openai.OpenAI")
    def test_gemini_shortcut(self, mock_openai_cls):
        from readpile.sync.llm import generate

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="ok"))]
        )

        config = {"llm": {"base_url": "gemini", "model": "gemini-2.0-flash"}}
        generate("system", "user", config)

        call_kwargs = mock_openai_cls.call_args[1]
        assert call_kwargs["base_url"] == "https://generativelanguage.googleapis.com/v1beta/openai/"

    @patch.dict("os.environ", {"READPILE_LLM_API_KEY": "key"}, clear=True)
    @patch("openai.OpenAI")
    def test_full_url_passed_through(self, mock_openai_cls):
        from readpile.sync.llm import generate

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="ok"))]
        )

        config = {"llm": {"base_url": "https://my-proxy.example.com/v1", "model": "my-model"}}
        generate("system", "user", config)

        call_kwargs = mock_openai_cls.call_args[1]
        assert call_kwargs["base_url"] == "https://my-proxy.example.com/v1"

    @patch.dict("os.environ", {}, clear=True)
    @patch("openai.OpenAI")
    def test_localhost_url_skips_api_key_check(self, mock_openai_cls):
        from readpile.sync.llm import generate

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="local"))]
        )

        config = {"llm": {"base_url": "http://localhost:8080/v1", "model": "local-model"}}
        result = generate("sys", "usr", config)
        assert result == "local"


# --- Message passing ---


class TestMessagePassing:
    @patch.dict("os.environ", {"READPILE_LLM_API_KEY": "test-key"}, clear=True)
    @patch("openai.OpenAI")
    def test_passes_system_and_user_prompts(self, mock_openai_cls):
        from readpile.sync.llm import generate

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="done"))]
        )

        config = {"llm": {"base_url": "anthropic", "model": "claude-sonnet-4-6"}}
        generate("You are helpful.", "Summarize this.", config)

        create_kwargs = mock_client.chat.completions.create.call_args[1]
        assert create_kwargs["messages"] == [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Summarize this."},
        ]
        assert create_kwargs["model"] == "claude-sonnet-4-6"

    @patch.dict("os.environ", {"READPILE_LLM_API_KEY": "test-key"}, clear=True)
    @patch("openai.OpenAI")
    def test_returns_empty_string_for_none_content(self, mock_openai_cls):
        from readpile.sync.llm import generate

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=None))]
        )

        config = {"llm": {"base_url": "anthropic", "model": "claude-sonnet-4-6"}}
        result = generate("sys", "usr", config)
        assert result == ""


# --- Retry on transient errors ---


class TestRetry:
    @patch("readpile.sync.llm.time.sleep")
    @patch.dict("os.environ", {"READPILE_LLM_API_KEY": "test-key"}, clear=True)
    @patch("openai.OpenAI")
    def test_retries_on_429(self, mock_openai_cls, mock_sleep):
        from readpile.sync.llm import generate
        from openai import APIStatusError

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}
        error = APIStatusError(
            message="Rate limited",
            response=mock_response,
            body=None,
        )

        mock_client.chat.completions.create.side_effect = [
            error,
            error,
            MagicMock(choices=[MagicMock(message=MagicMock(content="success"))]),
        ]

        config = {"llm": {"base_url": "anthropic", "model": "claude-sonnet-4-6"}}
        result = generate("sys", "usr", config)

        assert result == "success"
        assert mock_client.chat.completions.create.call_count == 3
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)

    @patch("readpile.sync.llm.time.sleep")
    @patch.dict("os.environ", {"READPILE_LLM_API_KEY": "test-key"}, clear=True)
    @patch("openai.OpenAI")
    def test_retries_on_500(self, mock_openai_cls, mock_sleep):
        from readpile.sync.llm import generate
        from openai import APIStatusError

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.headers = {}
        error = APIStatusError(
            message="Server error",
            response=mock_response,
            body=None,
        )

        mock_client.chat.completions.create.side_effect = [
            error,
            MagicMock(choices=[MagicMock(message=MagicMock(content="ok"))]),
        ]

        config = {"llm": {"model": "gpt-4o"}}
        result = generate("sys", "usr", config)

        assert result == "ok"
        assert mock_client.chat.completions.create.call_count == 2

    @patch("readpile.sync.llm.time.sleep")
    @patch.dict("os.environ", {"READPILE_LLM_API_KEY": "test-key"}, clear=True)
    @patch("openai.OpenAI")
    def test_exhausts_retries_raises(self, mock_openai_cls, mock_sleep):
        from readpile.sync.llm import generate
        from openai import APIStatusError

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}
        error = APIStatusError(
            message="Rate limited",
            response=mock_response,
            body=None,
        )

        mock_client.chat.completions.create.side_effect = [error, error, error]

        config = {"llm": {"base_url": "anthropic", "model": "claude-sonnet-4-6"}}
        with pytest.raises(APIStatusError):
            generate("sys", "usr", config)

        assert mock_client.chat.completions.create.call_count == 3
        assert mock_sleep.call_count == 3

    @patch.dict("os.environ", {"READPILE_LLM_API_KEY": "test-key"}, clear=True)
    @patch("openai.OpenAI")
    def test_non_transient_error_raises_immediately(self, mock_openai_cls):
        from readpile.sync.llm import generate
        from openai import APIStatusError

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.headers = {}
        error = APIStatusError(
            message="Unauthorized",
            response=mock_response,
            body=None,
        )

        mock_client.chat.completions.create.side_effect = error

        config = {"llm": {"base_url": "anthropic", "model": "claude-sonnet-4-6"}}
        with pytest.raises(APIStatusError):
            generate("sys", "usr", config)

        assert mock_client.chat.completions.create.call_count == 1


# --- API key checks ---


class TestAPIKeyChecks:
    @patch.dict("os.environ", {}, clear=True)
    def test_missing_api_key_raises_for_remote_url(self):
        from readpile.sync.llm import generate

        config = {"llm": {"base_url": "anthropic", "model": "claude-sonnet-4-6"}}
        with pytest.raises(RuntimeError, match="READPILE_LLM_API_KEY"):
            generate("sys", "usr", config)

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_api_key_raises_for_no_base_url(self):
        from readpile.sync.llm import generate

        config = {"llm": {"model": "gpt-4o"}}
        with pytest.raises(RuntimeError, match="READPILE_LLM_API_KEY"):
            generate("sys", "usr", config)

    @patch.dict("os.environ", {}, clear=True)
    @patch("openai.OpenAI")
    def test_local_url_skips_api_key_check(self, mock_openai_cls):
        from readpile.sync.llm import generate

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="local response"))]
        )

        config = {"llm": {"base_url": "ollama", "model": "llama3"}}
        result = generate("sys", "usr", config)
        assert result == "local response"

    @patch.dict("os.environ", {}, clear=True)
    @patch("openai.OpenAI")
    def test_api_key_from_config_dict(self, mock_openai_cls):
        from readpile.sync.llm import generate

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="ok"))]
        )

        config = {
            "llm": {
                "base_url": "anthropic",
                "model": "claude-sonnet-4-6",
                "api_key": "from-config",
            }
        }
        generate("sys", "usr", config)

        call_kwargs = mock_openai_cls.call_args[1]
        assert call_kwargs["api_key"] == "from-config"
