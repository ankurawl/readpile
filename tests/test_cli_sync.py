"""Tests for CLI sync commands via typer.testing.CliRunner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from readpile.cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Help output tests
# ---------------------------------------------------------------------------


class TestHelpOutput:
    """Verify that --help shows the expected subcommands."""

    def test_readpile_help_shows_sync_commands(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "sync" in result.output
        assert "synthesize" in result.output
        assert "feeds" in result.output
        assert "status" in result.output

    def test_feeds_help_shows_subcommands(self):
        result = runner.invoke(app, ["feeds", "--help"])
        assert result.exit_code == 0
        assert "add" in result.output
        assert "list" in result.output
        assert "remove" in result.output
        assert "enable" in result.output

    def test_sync_help_shows_options(self):
        result = runner.invoke(app, ["sync", "--help"])
        assert result.exit_code == 0
        assert "--dry-run" in result.output
        assert "--no-email" in result.output
        assert "--no-feeds" in result.output
        assert "--no-digest" in result.output
        assert "--reset-feeds" in result.output

    def test_synthesize_help_shows_options(self):
        result = runner.invoke(app, ["synthesize", "--help"])
        assert result.exit_code == 0
        assert "--pending" in result.output
        assert "--all" in result.output
        assert "--source" in result.output
        assert "--dry-run" in result.output


# ---------------------------------------------------------------------------
# feeds list
# ---------------------------------------------------------------------------


class TestFeedsList:
    """readpile feeds list with mocked registry."""

    def test_feeds_list_empty(self):
        with patch(
            "readpile.core.config.get_config_path",
            return_value=Path("/tmp/fake/config.toml"),
        ), patch(
            "readpile.sync.sources.FeedRegistry.load",
            return_value=[],
        ):
            result = runner.invoke(app, ["feeds", "list"])

        assert result.exit_code == 0
        assert "No feeds configured" in result.output

    def test_feeds_list_with_entries(self):
        from readpile.sync.sources import Feed

        feeds = [
            Feed(name="My Blog", url="https://blog.example.com/feed.xml", kind="rss"),
            Feed(
                name="ML Podcast", url="https://podcast.example.com/feed",
                kind="podcast", synthesize=False,
            ),
            Feed(
                name="Old Feed", url="https://old.example.com/rss",
                kind="rss", disabled=True,
            ),
        ]

        with patch(
            "readpile.core.config.get_config_path",
            return_value=Path("/tmp/fake/config.toml"),
        ), patch(
            "readpile.sync.sources.FeedRegistry.load",
            return_value=feeds,
        ):
            result = runner.invoke(app, ["feeds", "list"])

        assert result.exit_code == 0
        assert "1. My Blog" in result.output
        assert "2. ML Podcast" in result.output
        assert "3. Old Feed" in result.output
        assert "rss" in result.output
        assert "ML Podcast" in result.output
        assert "[no-synth]" in result.output
        assert "Old Feed" in result.output
        assert "[disabled]" in result.output


# ---------------------------------------------------------------------------
# feeds remove
# ---------------------------------------------------------------------------


class TestFeedsRemove:
    """readpile feeds remove with indices, ranges, and names."""

    def test_feeds_remove_by_index(self, tmp_path):
        from readpile.sync.sources import Feed

        feeds = [
            Feed(name="Feed 1", url="https://1.com", kind="rss"),
            Feed(name="Feed 2", url="https://2.com", kind="rss"),
        ]

        with patch("readpile.core.config.get_config_path", return_value=tmp_path / "config.toml"), \
             patch("readpile.sync.sources.FeedRegistry.load", return_value=feeds), \
             patch("readpile.sync.sources.FeedRegistry.remove_by_url") as mock_remove:
            
            result = runner.invoke(app, ["feeds", "remove", "1"])
            assert result.exit_code == 0
            mock_remove.assert_called_once_with("https://1.com")
            assert "Removed: Feed 1" in result.output

    def test_feeds_remove_by_range(self, tmp_path):
        from readpile.sync.sources import Feed

        feeds = [
            Feed(name="F1", url="https://1.com", kind="rss"),
            Feed(name="F2", url="https://2.com", kind="rss"),
            Feed(name="F3", url="https://3.com", kind="rss"),
        ]

        with patch("readpile.core.config.get_config_path", return_value=tmp_path / "config.toml"), \
             patch("readpile.sync.sources.FeedRegistry.load", return_value=feeds), \
             patch("readpile.sync.sources.FeedRegistry.remove_by_url") as mock_remove:
            
            result = runner.invoke(app, ["feeds", "remove", "1, 3"])
            assert result.exit_code == 0
            assert mock_remove.call_count == 2
            mock_remove.assert_any_call("https://1.com")
            mock_remove.assert_any_call("https://3.com")

    def test_feeds_remove_by_name_fallback(self, tmp_path):
        from readpile.sync.sources import Feed

        feeds = [
            Feed(name="Special Name", url="https://special.com", kind="rss"),
        ]

        with patch("readpile.core.config.get_config_path", return_value=tmp_path / "config.toml"), \
             patch("readpile.sync.sources.FeedRegistry.load", return_value=feeds), \
             patch("readpile.sync.sources.FeedRegistry.remove_by_url") as mock_remove:
            
            result = runner.invoke(app, ["feeds", "remove", "Special Name"])
            assert result.exit_code == 0
            mock_remove.assert_called_once_with("https://special.com")


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


class TestStatus:
    """readpile status with mocked state and sources."""

    def test_status_shows_overview(self, tmp_path):
        from readpile.sync.sources import Feed

        feeds = [
            Feed(name="Feed A", url="https://a.example.com/feed", kind="rss"),
            Feed(
                name="Feed B", url="https://b.example.com/feed",
                kind="rss", disabled=True,
            ),
        ]

        # Create a minimal wiki dir for the status command
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        (wiki_dir / ".wiki.toml").write_text(
            'name = "test"\ncategories = ["concept"]\n'
        )
        (wiki_dir / "pages").mkdir()
        (wiki_dir / "index.md").write_text("# Index\n")
        (wiki_dir / "log.md").write_text("# Log\n")

        # Build a mock config
        state_file = tmp_path / "sync-state.json"
        mock_config = {
            "sync": {
                "state_file": str(state_file),
                "log_file": str(tmp_path / "sync.log"),
            },
            "wiki": {"default_dir": str(wiki_dir)},
        }

        with patch(
            "readpile.core.config.load_config",
            return_value=mock_config,
        ), patch(
            "readpile.core.config.get_config_path",
            return_value=tmp_path / "config.toml",
        ), patch(
            "readpile.sync.sources.FeedRegistry.load",
            return_value=feeds,
        ):
            result = runner.invoke(app, ["status", "--wiki", str(wiki_dir)])

        assert result.exit_code == 0
        assert "Last sync" in result.output
        assert "Pending synthesis" in result.output
        assert "Feed A" in result.output
        assert "Feed B" in result.output

    def test_status_no_wiki(self, tmp_path):
        """Status works even when wiki dir does not exist."""
        mock_config = {
            "sync": {
                "state_file": str(tmp_path / "sync-state.json"),
                "log_file": str(tmp_path / "sync.log"),
            },
            "wiki": {"default_dir": str(tmp_path / "nonexistent")},
        }

        with patch(
            "readpile.core.config.load_config",
            return_value=mock_config,
        ), patch(
            "readpile.core.config.get_config_path",
            return_value=tmp_path / "config.toml",
        ), patch(
            "readpile.sync.sources.FeedRegistry.load",
            return_value=[],
        ):
            result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "Last sync" in result.output


# ---------------------------------------------------------------------------
# sync command (basic invocation tests)
# ---------------------------------------------------------------------------


class TestSyncCommand:
    """Basic invocation tests for the sync command."""

    def test_sync_no_wiki_errors(self, tmp_path):
        """sync errors when no wiki is found."""
        mock_config = {
            "sync": {},
            "wiki": {"default_dir": str(tmp_path / "nonexistent")},
        }

        with patch(
            "readpile.core.config.load_config",
            return_value=mock_config,
        ):
            result = runner.invoke(app, ["sync", "--wiki", str(tmp_path / "nonexistent")])

        assert result.exit_code == 1
        assert "No wiki found" in result.output
