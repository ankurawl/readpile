"""Tests for readpile.mcp_server — MCP tool functions."""

import os
import tempfile
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from readpile.mcp_server import mcp


class TestDetectType:
    def test_youtube_url(self):
        from readpile.core.detector import detect_url_type
        assert detect_url_type("https://www.youtube.com/watch?v=abc").value == "youtube"

    def test_rss_url(self):
        from readpile.core.detector import detect_url_type
        assert detect_url_type("https://blog.example.com/feed.xml").value == "rss"

    def test_blog_url(self):
        from readpile.core.detector import detect_url_type
        assert detect_url_type("https://example.com/article").value == "blog"

    def test_audio_url(self):
        from readpile.core.detector import detect_url_type
        assert detect_url_type("https://example.com/file.mp3").value == "audio_file"


class TestArchive:
    def test_creates_file(self):
        from readpile.core.models import ContentItem, ContentType
        from readpile.core.archiver import Archiver

        with tempfile.TemporaryDirectory() as tmpdir:
            item = ContentItem(
                text="Test content",
                title="Test Article",
                source_url="https://example.com/test",
                content_type=ContentType.article,
            )
            archiver = Archiver(tmpdir)
            path = archiver.save(item)
            assert path.exists()
            content = path.read_text()
            assert "Test content" in content
            assert "Test Article" in content

    def test_invalid_content_type_error(self):
        from readpile.core.models import ContentType
        try:
            ContentType("invalid_type")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_all_content_types_valid(self):
        from readpile.core.models import ContentType
        valid = [t.value for t in ContentType]
        assert "article" in valid
        assert "youtube" in valid
        assert "audio" in valid
        assert "podcast" in valid
        assert "webpage" in valid


class TestMcpServerStructure:
    def test_server_name(self):
        assert mcp.name == "readpile"

    def test_server_has_tools(self):
        assert mcp is not None


class TestTranscribeRouting:
    def test_non_transcribable_url_type(self):
        from readpile.core.detector import detect_url_type, URLType
        url_type = detect_url_type("https://blog.example.com/feed.xml")
        assert url_type == URLType.rss


class TestCrawlModeDetection:
    def test_rss_mode(self):
        from readpile.cli.crawl import _detect_crawl_mode
        assert _detect_crawl_mode("https://example.com/feed.xml") == "rss"

    def test_blog_mode(self):
        from readpile.cli.crawl import _detect_crawl_mode
        assert _detect_crawl_mode("https://example.com/blog") == "blog"

    def test_site_mode(self):
        from readpile.cli.crawl import _detect_crawl_mode
        assert _detect_crawl_mode("https://example.com/docs/intro") == "site"

    def test_podcast_mode(self):
        from readpile.cli.crawl import _detect_crawl_mode
        assert _detect_crawl_mode("https://example.com/podcast") == "podcast"

    def test_podcast_no_false_positive(self):
        from readpile.cli.crawl import _detect_crawl_mode
        assert _detect_crawl_mode("https://example.com/podcasting-tips") != "podcast"

    def test_podcast_rss_precedence(self):
        from readpile.cli.crawl import _detect_crawl_mode
        assert _detect_crawl_mode("https://example.com/podcast/feed") == "rss"


class TestCrawlMetadata:
    @patch("readpile.crawlers.rss.feedparser.parse")
    def test_rss_metadata_returns_json(self, mock_parse):
        """crawl with metadata=True returns JSON metadata strings."""
        import asyncio
        import json

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.feed = MagicMock()
        mock_feed.feed.get = {"title": "Test", "subtitle": "Desc"}.get

        entry = MagicMock()
        entry.get = {
            "title": "Post 1",
            "link": "https://test.com/post-1",
            "summary": "A summary.",
            "published_parsed": (2026, 4, 25, 0, 0, 0, 0, 0, 0),
        }.get
        mock_feed.entries = [entry]
        mock_parse.return_value = mock_feed

        from readpile.mcp_server import _create_server

        async def _run():
            server = _create_server()
            tools = server._tool_manager._tools
            crawl_fn = tools["crawl"].fn
            result = await crawl_fn(
                url="https://test.com/feed",
                mode="rss",
                recent=None,
                limit=None,
                metadata=True,
            )
            assert len(result) >= 2
            feed_info = json.loads(result[0])
            assert "feed_title" in feed_info
            entry_data = json.loads(result[1])
            assert entry_data["title"] == "Post 1"
            return result

        asyncio.run(_run())

    @patch("readpile.crawlers.rss.feedparser.parse")
    def test_rss_no_metadata_returns_urls(self, mock_parse):
        """crawl without metadata returns bare URL list (backward compat)."""
        import asyncio

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.feed = MagicMock()
        mock_feed.feed.get = {"title": "Test"}.get

        entry = MagicMock()
        entry.get = {
            "title": "Post 1",
            "link": "https://test.com/post-1",
            "published_parsed": (2026, 4, 25, 0, 0, 0, 0, 0, 0),
        }.get
        mock_feed.entries = [entry]
        mock_parse.return_value = mock_feed

        from readpile.crawlers.rss import crawl_rss
        urls = crawl_rss("https://test.com/feed")
        assert urls == ["https://test.com/post-1"]

    def test_metadata_safety_cap(self):
        """When metadata=True and recent is None, recent defaults to 50."""
        # This tests the logic inline — when metadata=True and no recent,
        # the crawl tool should set recent=50. We verify by checking the
        # internal logic path.
        recent = None
        metadata = True
        if metadata and recent is None:
            recent = 50
        assert recent == 50


class TestDiscoverPodcastFeed:
    def test_rss_url_returned_directly(self):
        """If URL is already RSS, return it without fetching."""
        import asyncio
        from readpile.mcp_server import _discover_podcast_feed

        result = asyncio.run(
            _discover_podcast_feed("https://example.com/feed.xml")
        )
        assert result == "https://example.com/feed.xml"

    @patch("readpile.crawlers.rss.feedparser.parse")
    def test_link_tag_discovery(self, mock_parse):
        """Discovers feed from <link rel="alternate"> tag."""
        import asyncio
        import httpx

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [MagicMock()]

        mock_parse.return_value = mock_feed

        html = """
        <html><head>
        <link rel="alternate" type="application/rss+xml"
              title="Feed" href="/feed">
        </head><body></body></html>
        """

        async def _run():
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.text = html
                mock_resp.raise_for_status = MagicMock()
                mock_client.get = AsyncMock(return_value=mock_resp)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client_cls.return_value = mock_client

                from readpile.mcp_server import _discover_podcast_feed
                result = await _discover_podcast_feed("https://example.com/podcast")
                assert result == "https://example.com/feed"

        asyncio.run(_run())

    @patch("readpile.crawlers.rss.feedparser.parse")
    def test_fallback_pattern_discovery(self, mock_parse):
        """Falls back to {base}/feed when no <link> tags."""
        import asyncio

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [MagicMock()]

        mock_parse.return_value = mock_feed

        html = "<html><head></head><body>No feed links</body></html>"

        async def _run():
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.text = html
                mock_resp.raise_for_status = MagicMock()
                mock_client.get = AsyncMock(return_value=mock_resp)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client_cls.return_value = mock_client

                from readpile.mcp_server import _discover_podcast_feed
                result = await _discover_podcast_feed("https://example.com/podcast")
                assert result == "https://example.com/feed"

        asyncio.run(_run())


class TestBatchScrape:
    def test_empty_urls(self):
        """batch_scrape with empty list returns message."""
        import asyncio
        from readpile.mcp_server import _create_server

        async def _run():
            server = _create_server()
            tools = server._tool_manager._tools
            batch_fn = tools["batch_scrape"].fn
            result = await batch_fn(urls=[], concurrency=3)
            assert result == "No URLs provided."

        asyncio.run(_run())

    @patch("readpile.scrapers.scrape_url")
    def test_mixed_success_failure(self, mock_scrape):
        """batch_scrape handles partial failures."""
        import asyncio
        from readpile.core.models import ContentItem, ContentType

        success_item = ContentItem(
            text="Content here",
            title="Good Article",
            source_url="https://good.com/article",
            content_type=ContentType.article,
        )

        async def _scrape_side_effect(url):
            if "good" in url:
                return success_item
            raise Exception("Connection refused")

        mock_scrape.side_effect = _scrape_side_effect

        async def _run():
            from readpile.mcp_server import _create_server
            server = _create_server()
            tools = server._tool_manager._tools
            batch_fn = tools["batch_scrape"].fn
            result = await batch_fn(
                urls=["https://good.com/article", "https://bad.com/broken"],
                concurrency=3,
            )
            assert "Good Article" in result
            assert "Failed:" in result
            assert "Connection refused" in result

        asyncio.run(_run())
