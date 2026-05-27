"""Tests for readpile senders CLI module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest
import tomlkit
from typer.testing import CliRunner

from readpile.cli.main import app

runner = CliRunner()


@pytest.fixture
def mock_config(tmp_path):
    config_dir = tmp_path / ".readpile"
    config_dir.mkdir()
    config_path = config_dir / "config.toml"
    
    # Initial config
    doc = tomlkit.document()
    sync = tomlkit.table()
    email = tomlkit.table()
    email.add("trusted_senders", ["existing@example.com"])
    sync.add("email", email)
    doc.add("sync", sync)
    config_path.write_text(tomlkit.dumps(doc), encoding="utf-8")
    
    with patch("readpile.core.config.get_config_path", return_value=config_path):
        yield config_path


def test_senders_list(mock_config):
    result = runner.invoke(app, ["senders", "list"])
    assert result.exit_code == 0
    assert "existing@example.com" in result.output


def test_senders_add(mock_config):
    result = runner.invoke(app, ["senders", "add", "new@example.com"])
    assert result.exit_code == 0
    assert "Added new@example.com" in result.output
    
    # Verify file
    doc = tomlkit.parse(mock_config.read_text())
    senders = doc["sync"]["email"]["trusted_senders"]
    assert "new@example.com" in senders


def test_senders_add_duplicate(mock_config):
    result = runner.invoke(app, ["senders", "add", "EXISTING@example.com"])
    assert result.exit_code == 0
    assert "already trusted" in result.output


def test_senders_remove(mock_config):
    result = runner.invoke(app, ["senders", "remove", "existing@example.com"])
    assert result.exit_code == 0
    assert "Removed existing@example.com" in result.output
    
    # Verify file
    doc = tomlkit.parse(mock_config.read_text())
    senders = doc["sync"]["email"]["trusted_senders"]
    assert "existing@example.com" not in senders


def test_senders_remove_not_found(mock_config):
    result = runner.invoke(app, ["senders", "remove", "missing@example.com"])
    assert result.exit_code == 0
    assert "not found" in result.output


@patch("readpile.sync.pipeline.SyncPipeline")
@patch("readpile.sync.sources.FeedRegistry")
def test_senders_scan_no_results(mock_registry, mock_pipeline, mock_config):
    # Mock config to have email enabled
    doc = tomlkit.parse(mock_config.read_text())
    doc["sync"]["email"]["enabled"] = True
    mock_config.write_text(tomlkit.dumps(doc))
    
    mock_registry_inst = mock_registry.return_value
    mock_registry_inst.load.return_value = []
    
    # Mock pipeline and provider
    mock_provider_inst = AsyncMock()
    mock_provider_inst.fetch_messages.return_value = []
    
    mock_pipeline_inst = mock_pipeline.return_value
    mock_pipeline_inst._get_email_provider = AsyncMock(return_value=mock_provider_inst)
    
    result = runner.invoke(app, ["senders", "scan"])
    if result.exit_code != 0:
        print(result.output)
    assert result.exit_code == 0
    assert "No new untrusted senders found" in result.output
