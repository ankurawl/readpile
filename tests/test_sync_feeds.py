"""Tests for readpile.sync.feeds.FeedProcessor."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from readpile.sync.sources import Feed, FeedRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def state_dir(tmp_path: Path) -> Path:
    d = tmp_path / "state"
    d.mkdir()
    return d


@pytest.fixture()
def wiki_dir(tmp_path: Path) -> Path:
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "sources").mkdir()
    return wiki


def _write_state(state_dir: Path, feeds: dict | None = None) -> None:
    data = {
        "version": 1,
        "last_sync": None,
        "email": {"seen_ids": []},
        "feeds": feeds or {},
        "saved_urls": [],
        "synthesis": {
            "pending": {},
            "synthesized": {},
            "skipped": {},
            "failed": {},
        },
        "digest": {"history": []},
    }
    (state_dir / "sync-state.json").write_text(json.dumps(data))


def _make_feed(
    name: str = "TestFeed",
    url: str = "https://example.com/feed.xml",
    kind: str = "rss",
    disabled: bool = False,
    synthesize: bool = True,
) -> Feed:
    return Feed(
        name=name, url=url, kind=kind,
        disabled=disabled, synthesize=synthesize,
    )


def _make_feed_entries(count: int, url_prefix: str = "https://example.com/post-") -> list[dict]:
    """Build a list of mock feed entries."""
    return [
        {
            "title": f"Post {i}",
            "url": f"{url_prefix}{i}",
            "date": f"2025-05-{10 + i:02d}",
            "author": "Author",
            "type": "article",
            "audio_url": None,
            "duration": None,
            "description": f"Description {i}",
        }
        for i in range(count)
    ]


def _make_feed_info(href: str | None = None) -> dict:
    info = {
        "feed_title": "Test Feed",
        "feed_description": "A test feed",
        "episode_count": 0,
    }
    if href:
        info["href"] = href
    return info


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBasicProcessing:
    """FeedProcessor returns entries from mocked crawl_rss_detailed."""

    @pytest.mark.asyncio
    async def test_returns_entries(self, state_dir, wiki_dir):
        _write_state(state_dir)
        feed = _make_feed()
        entries = _make_feed_entries(3)
        feed_info = _make_feed_info()

        from readpile.sync.state import SyncState
        from readpile.sync.feeds import FeedProcessor

        state = SyncState(state_dir / "sync-state.json", wiki_dir=wiki_dir)

        with patch(
            "readpile.crawlers.rss.crawl_rss_detailed",
            return_value=(feed_info, entries),
        ):
            processor = FeedProcessor([feed], state, {}, registry=None)
            results = await processor.check_all()

        assert len(results) == 3
        assert results[0].url == "https://example.com/post-0"
        assert results[0].title == "Post 0"
        assert results[0].source is feed


class TestFiltersSeenURLs:
    """Already-seen URLs are filtered out."""

    @pytest.mark.asyncio
    async def test_seen_urls_filtered(self, state_dir, wiki_dir):
        _write_state(state_dir, feeds={
            "https://example.com/feed.xml": {
                "seen_urls": ["https://example.com/post-0", "https://example.com/post-1"],
                "consecutive_failures": 0,
            },
        })
        feed = _make_feed()
        entries = _make_feed_entries(3)
        feed_info = _make_feed_info()

        from readpile.sync.state import SyncState
        from readpile.sync.feeds import FeedProcessor

        state = SyncState(state_dir / "sync-state.json", wiki_dir=wiki_dir)

        with patch(
            "readpile.crawlers.rss.crawl_rss_detailed",
            return_value=(feed_info, entries),
        ):
            processor = FeedProcessor([feed], state, {}, registry=None)
            results = await processor.check_all()

        assert len(results) == 1
        assert results[0].url == "https://example.com/post-2"


class TestFirstSyncEntryCap:
    """On first sync, only max_initial_entries are processed."""

    @pytest.mark.asyncio
    async def test_first_sync_caps_at_20(self, state_dir, wiki_dir):
        _write_state(state_dir)
        feed = _make_feed()
        entries = _make_feed_entries(100)
        feed_info = _make_feed_info()

        config = {"sync": {"max_initial_entries": 20}}

        from readpile.sync.state import SyncState
        from readpile.sync.feeds import FeedProcessor

        state = SyncState(state_dir / "sync-state.json", wiki_dir=wiki_dir)

        with patch(
            "readpile.crawlers.rss.crawl_rss_detailed",
            return_value=(feed_info, entries),
        ):
            processor = FeedProcessor([feed], state, config, registry=None)
            results = await processor.check_all()

        assert len(results) == 20
        # The remaining 80 should still be marked as seen
        seen = state.get_feed_seen_urls(feed.url)
        assert len(seen) == 100


class TestFeedRedirectDetection:
    """When feed_info href differs from feed URL, update_url is called."""

    @pytest.mark.asyncio
    async def test_redirect_updates_url(self, state_dir, wiki_dir, tmp_path):
        _write_state(state_dir)
        feed = _make_feed()
        entries = _make_feed_entries(1)
        new_url = "https://example.com/feed-v2.xml"
        feed_info = _make_feed_info(href=new_url)

        from readpile.sync.state import SyncState
        from readpile.sync.feeds import FeedProcessor

        state = SyncState(state_dir / "sync-state.json", wiki_dir=wiki_dir)

        mock_registry = MagicMock(spec=FeedRegistry)

        with patch(
            "readpile.crawlers.rss.crawl_rss_detailed",
            return_value=(feed_info, entries),
        ):
            processor = FeedProcessor(
                [feed], state, {}, registry=mock_registry,
            )
            await processor.check_all()

        mock_registry.update_url.assert_called_once_with(feed.name, new_url)


class TestConsecutiveFailureTracking:
    """After max_consecutive_failures, the feed is auto-disabled."""

    @pytest.mark.asyncio
    async def test_seven_failures_disables_feed(self, state_dir, wiki_dir):
        # Pre-set 6 consecutive failures
        _write_state(state_dir, feeds={
            "https://example.com/feed.xml": {
                "seen_urls": [],
                "consecutive_failures": 6,
            },
        })
        feed = _make_feed()
        config = {"sync": {"max_consecutive_failures": 7}}

        from readpile.sync.state import SyncState
        from readpile.sync.feeds import FeedProcessor

        state = SyncState(state_dir / "sync-state.json", wiki_dir=wiki_dir)
        mock_registry = MagicMock(spec=FeedRegistry)

        with patch(
            "readpile.crawlers.rss.crawl_rss_detailed",
            side_effect=RuntimeError("network error"),
        ):
            processor = FeedProcessor(
                [feed], state, config, registry=mock_registry,
            )
            results = await processor.check_all()

        assert len(results) == 0
        mock_registry.disable.assert_called_once_with(feed.name)
        assert state.get_consecutive_failures(feed.url) == 7


class TestDisabledFeedSkipped:
    """A disabled feed is not crawled at all."""

    @pytest.mark.asyncio
    async def test_disabled_feed_skipped(self, state_dir, wiki_dir):
        _write_state(state_dir)
        feed = _make_feed(disabled=True)

        from readpile.sync.state import SyncState
        from readpile.sync.feeds import FeedProcessor

        state = SyncState(state_dir / "sync-state.json", wiki_dir=wiki_dir)

        with patch(
            "readpile.crawlers.rss.crawl_rss_detailed",
        ) as mock_crawl:
            processor = FeedProcessor([feed], state, {}, registry=None)
            results = await processor.check_all()

        assert len(results) == 0
        mock_crawl.assert_not_called()


class TestStateTracking:
    """mark_url_seen is called for each processed entry."""

    @pytest.mark.asyncio
    async def test_mark_url_seen_called(self, state_dir, wiki_dir):
        _write_state(state_dir)
        feed = _make_feed()
        entries = _make_feed_entries(3)
        feed_info = _make_feed_info()

        from readpile.sync.state import SyncState
        from readpile.sync.feeds import FeedProcessor

        state = SyncState(state_dir / "sync-state.json", wiki_dir=wiki_dir)

        with patch(
            "readpile.crawlers.rss.crawl_rss_detailed",
            return_value=(feed_info, entries),
        ):
            processor = FeedProcessor([feed], state, {}, registry=None)
            await processor.check_all()

        seen = state.get_feed_seen_urls(feed.url)
        assert "https://example.com/post-0" in seen
        assert "https://example.com/post-1" in seen
        assert "https://example.com/post-2" in seen


class TestYouTubeFeedResolvesURL:
    """YouTube feeds call resolve_youtube_feed."""

    @pytest.mark.asyncio
    async def test_youtube_feed_resolves(self, state_dir, wiki_dir):
        _write_state(state_dir)
        feed = _make_feed(
            name="YT Channel",
            url="https://youtube.com/@example",
            kind="youtube",
        )
        entries = _make_feed_entries(1)
        feed_info = _make_feed_info()

        from readpile.sync.state import SyncState
        from readpile.sync.feeds import FeedProcessor

        state = SyncState(state_dir / "sync-state.json", wiki_dir=wiki_dir)

        resolved_feed = "https://www.youtube.com/feeds/videos.xml?channel_id=UC123"

        with (
            patch(
                "readpile.crawlers.discovery.resolve_youtube_feed",
                new_callable=AsyncMock,
                return_value=resolved_feed,
            ) as mock_resolve,
            patch(
                "readpile.crawlers.rss.crawl_rss_detailed",
                return_value=(feed_info, entries),
            ) as mock_crawl,
        ):
            processor = FeedProcessor([feed], state, {}, registry=None)
            results = await processor.check_feed(feed)

        mock_resolve.assert_called_once_with("https://youtube.com/@example")
        # crawl_rss_detailed should be called with the resolved feed URL
        call_args = mock_crawl.call_args
        assert call_args[0][0] == resolved_feed


class TestSuccessResetsFailures:
    """Successful crawl resets the failure counter."""

    @pytest.mark.asyncio
    async def test_success_resets_failures(self, state_dir, wiki_dir):
        _write_state(state_dir, feeds={
            "https://example.com/feed.xml": {
                "seen_urls": [],
                "consecutive_failures": 3,
            },
        })
        feed = _make_feed()
        entries = _make_feed_entries(1)
        feed_info = _make_feed_info()

        from readpile.sync.state import SyncState
        from readpile.sync.feeds import FeedProcessor

        state = SyncState(state_dir / "sync-state.json", wiki_dir=wiki_dir)

        with patch(
            "readpile.crawlers.rss.crawl_rss_detailed",
            return_value=(feed_info, entries),
        ):
            processor = FeedProcessor([feed], state, {}, registry=None)
            await processor.check_all()

        assert state.get_consecutive_failures(feed.url) == 0
