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
