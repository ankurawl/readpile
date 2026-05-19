"""Tests for readpile.core.config — load_config, get_config_path, defaults."""

import os
from pathlib import Path

from readpile.core.config import load_config, get_config_path, DEFAULTS


# --- Defaults ---


def test_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("READPILE_CONFIG", str(tmp_path / "nonexistent.toml"))
    config = load_config()
    assert config["general"]["auto_archive"] is False
    assert config["scrape"]["headless"] is True
    assert config["transcribe"]["engine"] == "auto"
    assert config["crawl"]["max_depth"] == 10
    assert config["wiki"]["default_dir"] == "~/my-wiki"
    assert "summarize" not in config


# --- get_config_path ---


def test_config_path_default():
    path = get_config_path()
    assert str(path).endswith("config.toml")


def test_config_path_env(monkeypatch):
    monkeypatch.setenv("READPILE_CONFIG", "/tmp/custom.toml")
    assert str(get_config_path()) == "/tmp/custom.toml"


# --- Environment variable override ---


def test_env_var_override(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "test-token-123")
    config = load_config()
    assert config["transcribe"]["hf_token"] == "test-token-123"


# --- TOML file loading ---


def test_toml_file_loading(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[scrape]\nheadless = false\n')
    monkeypatch.setenv("READPILE_CONFIG", str(config_file))
    config = load_config()
    assert config["scrape"]["headless"] is False
    assert config["transcribe"]["engine"] == "auto"


# --- CLI overrides ---


def test_cli_overrides():
    overrides = {"crawl": {"max_depth": 5}}
    config = load_config(cli_overrides=overrides)
    assert config["crawl"]["max_depth"] == 5
