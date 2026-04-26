"""Tests for mediakit.core.config — load_config, get_config_path, defaults."""

import os
from pathlib import Path

from mediakit.core.config import load_config, get_config_path, DEFAULTS


# --- Defaults ---


def test_defaults():
    config = load_config()
    assert config["summarize"]["provider"] == "ollama"
    assert config["scrape"]["headless"] is True
    assert config["transcribe"]["engine"] == "auto"
    assert config["crawl"]["max_depth"] == 10


# --- get_config_path ---


def test_config_path_default():
    path = get_config_path()
    assert str(path).endswith("config.toml")


def test_config_path_env(monkeypatch):
    monkeypatch.setenv("MEDIAKIT_CONFIG", "/tmp/custom.toml")
    assert str(get_config_path()) == "/tmp/custom.toml"


# --- Environment variable override ---


def test_env_var_override(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://custom:1234")
    config = load_config()
    assert config["summarize"]["ollama"]["host"] == "http://custom:1234"


# --- TOML file loading ---


def test_toml_file_loading(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[summarize]\nprovider = "claude"\n')
    monkeypatch.setenv("MEDIAKIT_CONFIG", str(config_file))
    config = load_config()
    assert config["summarize"]["provider"] == "claude"
    # Other defaults still present
    assert config["scrape"]["headless"] is True


# --- CLI overrides ---


def test_cli_overrides():
    overrides = {"summarize": {"provider": "openai"}}
    config = load_config(cli_overrides=overrides)
    assert config["summarize"]["provider"] == "openai"
