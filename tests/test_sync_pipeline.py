"""Tests for readpile.sync.pipeline.SyncPipeline."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture()
def wiki_dir(tmp_path: Path) -> Path:
    """Create a minimal wiki directory so the pipeline can run."""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / ".wiki.toml").write_text('name = "test"\ncategories = ["concept"]\n')
    (wiki / "pages").mkdir()
    (wiki / "sources").mkdir()
    (wiki / "index.md").write_text("# Index\n")
    (wiki / "log.md").write_text("# Log\n")
    return wiki


@pytest.fixture()
def config(tmp_path: Path) -> dict:
    state_file = tmp_path / "state" / "sync-state.json"
    log_file = tmp_path / "logs" / "sync.log"
    return {
        "sync": {
            "state_file": str(state_file),
            "log_file": str(log_file),
            "email": {"enabled": False},
            "digest": {"enabled": False},
        },
        "wiki": {"default_dir": ""},
        "scrape": {"rate_limit": 0},
    }


def _make_pipeline(config: dict, wiki_dir: Path, dry_run: bool = False):
    from readpile.sync.pipeline import SyncPipeline

    return SyncPipeline(config, wiki_dir, dry_run=dry_run)


# ---- helpers to build common patches ----

def _patch_setup_logging():
    return patch("readpile.sync.pipeline.SyncState.acquire_lock")


def _base_patches():
    """Return a list of context managers that mock away side-effects."""
    return [
        patch("readpile.sync.logging.setup_logging"),
        patch(
            "readpile.sync.sources.SourceRegistry.load",
            return_value=[],
        ),
        patch("readpile.core.config.get_config_path", return_value=Path("/tmp/fake/config.toml")),
    ]


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------


class TestPipelineRunsCleanly:
    """Pipeline runs without errors when all components are mocked."""

    @pytest.mark.asyncio
    async def test_run_no_errors_all_mocked(self, config, wiki_dir, tmp_path):
        pipeline = _make_pipeline(config, wiki_dir)
        with (
            patch("readpile.sync.logging.setup_logging"),
            patch(
                "readpile.sync.sources.SourceRegistry.load",
                return_value=[],
            ),
            patch(
                "readpile.core.config.get_config_path",
                return_value=tmp_path / "config.toml",
            ),
        ):
            result = await pipeline.run()

        assert result.new_items == 0
        assert result.errors == []
        assert result.duration_seconds > 0

    @pytest.mark.asyncio
    async def test_sync_result_populated(self, config, wiki_dir, tmp_path):
        """SyncResult fields are populated correctly after a run."""
        pipeline = _make_pipeline(config, wiki_dir)
        with (
            patch("readpile.sync.logging.setup_logging"),
            patch(
                "readpile.sync.sources.SourceRegistry.load",
                return_value=[],
            ),
            patch(
                "readpile.core.config.get_config_path",
                return_value=tmp_path / "config.toml",
            ),
        ):
            result = await pipeline.run()

        assert result.email_count == 0
        assert result.feed_count == 0
        assert result.saved_paths == []
        assert result.skipped_unknown_senders == []
        assert isinstance(result.duration_seconds, float)


class TestSkipFlags:
    """--no-email, --no-feeds, --no-digest skip their respective stages."""

    @pytest.mark.asyncio
    async def test_no_email_skips_email_stage(self, config, wiki_dir, tmp_path):
        config["sync"]["email"]["enabled"] = True
        pipeline = _make_pipeline(config, wiki_dir)

        with (
            patch("readpile.sync.logging.setup_logging"),
            patch(
                "readpile.sync.sources.SourceRegistry.load",
                return_value=[],
            ),
            patch(
                "readpile.core.config.get_config_path",
                return_value=tmp_path / "config.toml",
            ),
            patch.object(
                pipeline, "_get_email_provider", new_callable=AsyncMock,
            ) as mock_email,
        ):
            result = await pipeline.run(no_email=True)

        mock_email.assert_not_called()
        assert result.email_count == 0

    @pytest.mark.asyncio
    async def test_no_feeds_skips_feed_stage(self, config, wiki_dir, tmp_path):
        pipeline = _make_pipeline(config, wiki_dir)

        with (
            patch("readpile.sync.logging.setup_logging"),
            patch(
                "readpile.sync.sources.SourceRegistry.load",
                return_value=[],
            ),
            patch(
                "readpile.core.config.get_config_path",
                return_value=tmp_path / "config.toml",
            ),
            patch.object(
                pipeline, "_crawl_feeds", new_callable=AsyncMock,
            ) as mock_feeds,
        ):
            result = await pipeline.run(no_feeds=True)

        mock_feeds.assert_not_called()
        assert result.feed_count == 0

    @pytest.mark.asyncio
    async def test_no_digest_skips_digest(self, config, wiki_dir, tmp_path):
        config["sync"]["digest"]["enabled"] = True
        pipeline = _make_pipeline(config, wiki_dir)

        with (
            patch("readpile.sync.logging.setup_logging"),
            patch(
                "readpile.sync.sources.SourceRegistry.load",
                return_value=[],
            ),
            patch(
                "readpile.core.config.get_config_path",
                return_value=tmp_path / "config.toml",
            ),
            patch.object(
                pipeline, "_send_digest", new_callable=AsyncMock,
            ) as mock_digest,
        ):
            result = await pipeline.run(no_digest=True)

        mock_digest.assert_not_called()


class TestDryRun:
    """--dry-run fetches but skips saving."""

    @pytest.mark.asyncio
    async def test_dry_run_does_not_save(self, config, wiki_dir, tmp_path):
        from readpile.sync.sources import Source

        source = Source(name="test", url="https://example.com/feed", kind="rss")

        # _crawl_feeds returns list[dict], not FeedResult
        feed_item = {
            "url": "https://example.com/article-1",
            "title": "Article 1",
            "content_type": "article",
            "date": None,
            "author": None,
            "source_type": "feed",
            "source_name": "test",
            "skip_synthesis": False,
        }

        pipeline = _make_pipeline(config, wiki_dir, dry_run=True)

        with (
            patch("readpile.sync.logging.setup_logging"),
            patch(
                "readpile.sync.sources.SourceRegistry.load",
                return_value=[source],
            ),
            patch(
                "readpile.core.config.get_config_path",
                return_value=tmp_path / "config.toml",
            ),
            patch.object(
                pipeline, "_crawl_feeds", new_callable=AsyncMock,
                return_value=[feed_item],
            ),
            patch.object(
                pipeline, "_save_item", new_callable=AsyncMock,
            ) as mock_save,
        ):
            result = await pipeline.run()

        mock_save.assert_not_called()
        assert result.new_items == 1
        assert result.saved_paths == []


class TestResetFeeds:
    """--reset-feeds clears feed state."""

    @pytest.mark.asyncio
    async def test_reset_feeds_clears_state(self, config, wiki_dir, tmp_path):
        pipeline = _make_pipeline(config, wiki_dir)

        with (
            patch("readpile.sync.logging.setup_logging"),
            patch(
                "readpile.sync.sources.SourceRegistry.load",
                return_value=[],
            ),
            patch(
                "readpile.core.config.get_config_path",
                return_value=tmp_path / "config.toml",
            ),
            patch(
                "readpile.sync.state.SyncState.reset_feeds",
            ) as mock_reset,
        ):
            await pipeline.run(reset_feeds=True)

        mock_reset.assert_called_once()


class TestLockManagement:
    """Lock is acquired and released around the pipeline run."""

    @pytest.mark.asyncio
    async def test_lock_acquired_and_released(self, config, wiki_dir, tmp_path):
        pipeline = _make_pipeline(config, wiki_dir)

        with (
            patch("readpile.sync.logging.setup_logging"),
            patch(
                "readpile.sync.sources.SourceRegistry.load",
                return_value=[],
            ),
            patch(
                "readpile.core.config.get_config_path",
                return_value=tmp_path / "config.toml",
            ),
            patch(
                "readpile.sync.state.SyncState.acquire_lock",
            ) as mock_acquire,
            patch(
                "readpile.sync.state.SyncState.release_lock",
            ) as mock_release,
        ):
            await pipeline.run()

        mock_acquire.assert_called_once()
        mock_release.assert_called_once()

    @pytest.mark.asyncio
    async def test_lock_released_on_error(self, config, wiki_dir, tmp_path):
        """Lock is released even when the pipeline raises."""
        pipeline = _make_pipeline(config, wiki_dir)

        with (
            patch("readpile.sync.logging.setup_logging"),
            patch(
                "readpile.sync.sources.SourceRegistry.load",
                side_effect=RuntimeError("boom"),
            ),
            patch(
                "readpile.core.config.get_config_path",
                return_value=tmp_path / "config.toml",
            ),
            patch(
                "readpile.sync.state.SyncState.acquire_lock",
            ),
            patch(
                "readpile.sync.state.SyncState.release_lock",
            ) as mock_release,
        ):
            with pytest.raises(RuntimeError, match="boom"):
                await pipeline.run()

        mock_release.assert_called_once()
