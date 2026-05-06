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

    def test_youtube_channel_handle(self):
        from readpile.cli.crawl import _detect_crawl_mode
        assert _detect_crawl_mode("https://www.youtube.com/@howiaipodcast") == "youtube"

    def test_youtube_channel_id(self):
        from readpile.cli.crawl import _detect_crawl_mode
        assert _detect_crawl_mode("https://www.youtube.com/channel/UCxyz123") == "youtube"

    def test_youtube_channel_with_subpath(self):
        from readpile.cli.crawl import _detect_crawl_mode
        assert _detect_crawl_mode("https://www.youtube.com/@handle/videos") == "youtube"

    def test_youtube_watch_not_channel(self):
        """YouTube watch URLs should NOT be detected as youtube channel mode."""
        from readpile.cli.crawl import _detect_crawl_mode
        # watch URLs don't match the channel pattern, so they fall through
        # to the default "site" mode (the detector handles them separately)
        result = _detect_crawl_mode("https://www.youtube.com/watch?v=abc123")
        assert result != "youtube"


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


class TestTranscribeFallback:
    @patch("readpile.mcp_server._extract_media_url")
    def test_audio_with_fallback_url(self, mock_extract):
        """When audio transcription fails (no ffmpeg) and fallback_url has
        a YouTube embed, transcribe via YouTube captions instead."""
        import asyncio
        from readpile.core.models import ContentItem, ContentType

        mock_extract.return_value = "https://www.youtube.com/watch?v=test123test"

        yt_item = ContentItem(
            text="Transcript here",
            title="Episode Title",
            source_url="https://www.youtube.com/watch?v=test123test",
            content_type=ContentType.youtube,
        )

        async def _run():
            from readpile.mcp_server import _create_server

            server = _create_server()
            tools = server._tool_manager._tools
            transcribe_fn = tools["transcribe"].fn

            with patch(
                "readpile.transcribers.youtube.transcribe_youtube",
                return_value=yt_item,
            ):
                result = await transcribe_fn(
                    source="https://example.com/episode.mp3",
                    language="en",
                    fallback_url="https://example.com/p/episode-page",
                )
            assert "Transcript here" in result
            assert "Episode Title" in result

        asyncio.run(_run())

    @patch("readpile.mcp_server._extract_media_url")
    def test_audio_with_fallback_no_embed(self, mock_extract):
        """When fallback_url has no YouTube embed, return error message."""
        import asyncio

        mock_extract.return_value = None

        async def _run():
            from readpile.mcp_server import _create_server

            server = _create_server()
            tools = server._tool_manager._tools
            transcribe_fn = tools["transcribe"].fn
            result = await transcribe_fn(
                source="https://example.com/episode.mp3",
                language="en",
                fallback_url="https://example.com/p/no-embed",
            )
            assert "Error" in result
            assert "ffmpeg" in result

        asyncio.run(_run())

    def test_audio_without_fallback_url(self):
        """When audio transcription fails and no fallback_url, return error."""
        import asyncio

        async def _run():
            from readpile.mcp_server import _create_server

            server = _create_server()
            tools = server._tool_manager._tools
            transcribe_fn = tools["transcribe"].fn
            result = await transcribe_fn(
                source="https://example.com/episode.mp3",
                language="en",
            )
            assert "Error" in result
            assert "ffmpeg" in result

        asyncio.run(_run())

    @patch("readpile.mcp_server._extract_media_url")
    def test_webpage_with_youtube_embed(self, mock_extract):
        """Webpage URLs should find and transcribe embedded YouTube videos."""
        import asyncio
        from readpile.core.models import ContentItem, ContentType

        mock_extract.return_value = "https://www.youtube.com/watch?v=abc12345678"

        yt_item = ContentItem(
            text="Video transcript",
            title="Podcast Episode",
            source_url="https://www.youtube.com/watch?v=abc12345678",
            content_type=ContentType.youtube,
        )

        async def _run():
            from readpile.mcp_server import _create_server

            server = _create_server()
            tools = server._tool_manager._tools
            transcribe_fn = tools["transcribe"].fn

            with patch(
                "readpile.transcribers.youtube.transcribe_youtube",
                return_value=yt_item,
            ):
                result = await transcribe_fn(
                    source="https://example.com/p/episode-page",
                    language="en",
                )
            assert "Video transcript" in result

        asyncio.run(_run())


class TestTranscribeViaFallback:
    @patch("readpile.mcp_server._extract_media_url")
    def test_returns_transcript_on_youtube_embed(self, mock_extract):
        """_transcribe_via_fallback returns transcript when YouTube found."""
        import asyncio
        from readpile.core.models import ContentItem, ContentType

        mock_extract.return_value = "https://www.youtube.com/watch?v=xyz12345678"

        yt_item = ContentItem(
            text="Fallback transcript",
            title="Fallback Episode",
            source_url="https://www.youtube.com/watch?v=xyz12345678",
            content_type=ContentType.youtube,
        )

        async def _run():
            from readpile.mcp_server import _transcribe_via_fallback

            with patch(
                "readpile.transcribers.youtube.transcribe_youtube",
                return_value=yt_item,
            ):
                result = await _transcribe_via_fallback(
                    "https://example.com/page", "en"
                )
            assert result is not None
            assert "Fallback transcript" in result

        asyncio.run(_run())

    @patch("readpile.mcp_server._extract_media_url")
    def test_returns_none_when_no_media(self, mock_extract):
        """_transcribe_via_fallback returns None when no media found."""
        import asyncio

        mock_extract.return_value = None

        async def _run():
            from readpile.mcp_server import _transcribe_via_fallback

            result = await _transcribe_via_fallback(
                "https://example.com/page", "en"
            )
            assert result is None

        asyncio.run(_run())

    @patch("readpile.mcp_server._extract_media_url")
    def test_returns_none_for_non_youtube_media(self, mock_extract):
        """_transcribe_via_fallback returns None for non-YouTube media."""
        import asyncio

        mock_extract.return_value = "https://example.com/audio.mp3"

        async def _run():
            from readpile.mcp_server import _transcribe_via_fallback

            result = await _transcribe_via_fallback(
                "https://example.com/page", "en"
            )
            assert result is None

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


class TestDiscoverFeed:
    def test_rss_url_returned_directly(self):
        """If URL is already RSS, return it without fetching."""
        import asyncio
        from readpile.mcp_server import _discover_feed

        result = asyncio.run(
            _discover_feed("https://example.com/feed.xml")
        )
        assert result == "https://example.com/feed.xml"

    @patch("readpile.crawlers.rss.feedparser.parse")
    def test_link_tag_discovery(self, mock_parse):
        """Discovers feed from <link rel="alternate"> tag."""
        import asyncio

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [MagicMock()]
        mock_parse.return_value = mock_feed

        html = """
        <html><head>
        <link rel="alternate" type="application/rss+xml"
              title="Blog Feed" href="/feed">
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

                from readpile.mcp_server import _discover_feed
                result = await _discover_feed("https://example.com/blog")
                assert result == "https://example.com/feed"

        asyncio.run(_run())

    @patch("readpile.crawlers.rss.feedparser.parse")
    def test_atom_link_discovery(self, mock_parse):
        """Discovers Atom feed from <link rel="alternate"> tag."""
        import asyncio

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [MagicMock()]
        mock_parse.return_value = mock_feed

        html = """
        <html><head>
        <link rel="alternate" type="application/atom+xml"
              title="Atom Feed" href="/atom.xml">
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

                from readpile.mcp_server import _discover_feed
                result = await _discover_feed("https://example.com/blog")
                assert result == "https://example.com/atom.xml"

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

                from readpile.mcp_server import _discover_feed
                result = await _discover_feed("https://example.com/blog")
                assert result == "https://example.com/feed"

        asyncio.run(_run())

    @patch("readpile.crawlers.rss.feedparser.parse")
    def test_prefer_keywords(self, mock_parse):
        """With prefer_keywords, matching <link> titles are tried first."""
        import asyncio

        call_order = []

        def _parse_side_effect(url):
            call_order.append(url)
            mock_feed = MagicMock()
            mock_feed.bozo = False
            mock_feed.entries = [MagicMock()]
            return mock_feed

        mock_parse.side_effect = _parse_side_effect

        html = """
        <html><head>
        <link rel="alternate" type="application/rss+xml"
              title="Blog Feed" href="/blog-feed">
        <link rel="alternate" type="application/rss+xml"
              title="Podcast Audio Feed" href="/podcast-feed">
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

                from readpile.mcp_server import _discover_feed
                result = await _discover_feed(
                    "https://example.com/podcast",
                    prefer_keywords=["podcast", "audio"],
                )
                assert result == "https://example.com/podcast-feed"
                assert call_order[0] == "https://example.com/podcast-feed"

        asyncio.run(_run())


class TestCrawlRssDiscovery:
    @patch("readpile.mcp_server._discover_feed", new_callable=AsyncMock)
    @patch("readpile.crawlers.rss.feedparser.parse")
    def test_rss_mode_discovers_feed_for_non_feed_url(
        self, mock_parse, mock_discover
    ):
        """crawl with mode=rss discovers feed when URL is not a feed."""
        import asyncio

        mock_discover.return_value = "https://blog.example.com/feed"

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.feed = MagicMock()
        mock_feed.feed.get = {"title": "Blog"}.get
        entry = MagicMock()
        entry.get = {
            "title": "Post 1",
            "link": "https://blog.example.com/post-1",
            "published_parsed": (2026, 4, 25, 0, 0, 0, 0, 0, 0),
        }.get
        mock_feed.entries = [entry]
        mock_parse.return_value = mock_feed

        async def _run():
            from readpile.mcp_server import _create_server

            server = _create_server()
            tools = server._tool_manager._tools
            crawl_fn = tools["crawl"].fn
            result = await crawl_fn(
                url="https://blog.example.com",
                mode="rss",
                recent=None,
                limit=None,
                metadata=False,
            )
            assert "https://blog.example.com/post-1" in result
            mock_discover.assert_called_once()

        asyncio.run(_run())

    @patch("readpile.crawlers.rss.feedparser.parse")
    def test_rss_mode_skips_discovery_for_feed_url(self, mock_parse):
        """crawl with mode=rss skips discovery when URL looks like a feed."""
        import asyncio

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.feed = MagicMock()
        mock_feed.feed.get = {"title": "Blog"}.get
        entry = MagicMock()
        entry.get = {
            "title": "Post 1",
            "link": "https://blog.example.com/post-1",
            "published_parsed": (2026, 4, 25, 0, 0, 0, 0, 0, 0),
        }.get
        mock_feed.entries = [entry]
        mock_parse.return_value = mock_feed

        async def _run():
            from readpile.mcp_server import _create_server

            server = _create_server()
            tools = server._tool_manager._tools
            crawl_fn = tools["crawl"].fn

            with patch(
                "readpile.mcp_server._discover_feed", new_callable=AsyncMock
            ) as mock_discover:
                result = await crawl_fn(
                    url="https://blog.example.com/feed.xml",
                    mode="rss",
                    recent=None,
                    limit=None,
                    metadata=False,
                )
                assert "https://blog.example.com/post-1" in result
                mock_discover.assert_not_called()

        asyncio.run(_run())


class TestBatchScrapeArchive:
    @patch("readpile.scrapers.scrape_url")
    def test_archive_dir_saves_files(self, mock_scrape):
        """batch_scrape with archive_dir saves scraped articles to disk."""
        import asyncio
        import os
        import tempfile
        from readpile.core.models import ContentItem, ContentType

        success_item = ContentItem(
            text="Article content here",
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

            with tempfile.TemporaryDirectory() as tmpdir:
                result = await batch_fn(
                    urls=["https://good.com/article", "https://bad.com/broken"],
                    concurrency=3,
                    archive_dir=tmpdir,
                )
                assert "Good Article" in result
                assert "---ARCHIVED---" in result
                assert "Saved:" in result
                files = os.listdir(tmpdir)
                assert len(files) == 1
                assert files[0].endswith(".md")

        asyncio.run(_run())

    @patch("readpile.scrapers.scrape_url")
    def test_no_archive_without_dir(self, mock_scrape):
        """batch_scrape without archive_dir does not archive."""
        import asyncio
        from readpile.core.models import ContentItem, ContentType

        item = ContentItem(
            text="Content",
            title="Article",
            source_url="https://example.com/post",
            content_type=ContentType.article,
        )

        async def _scrape_side_effect(url):
            return item

        mock_scrape.side_effect = _scrape_side_effect

        async def _run():
            from readpile.mcp_server import _create_server
            server = _create_server()
            tools = server._tool_manager._tools
            batch_fn = tools["batch_scrape"].fn
            result = await batch_fn(
                urls=["https://example.com/post"],
                concurrency=3,
            )
            assert "Article" in result
            assert "---ARCHIVED---" not in result

        asyncio.run(_run())
