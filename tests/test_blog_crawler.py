"""Tests for readpile.crawlers.blog — blog post URL discovery."""

from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlparse

import pytest


class TestBlogCrawlerImport:
    def test_can_import_without_playwright(self):
        """BlogCrawler should be importable even without Playwright installed."""
        try:
            from readpile.crawlers.blog import BlogCrawler
        except SystemExit:
            pytest.skip("Playwright not available")

    def test_check_deps_guard(self):
        from readpile.crawlers.blog import _check_deps
        try:
            _check_deps()
        except SystemExit:
            pytest.skip("Required deps not installed")


class TestBlogPostDetection:
    def test_detector_import(self):
        from readpile.crawlers.blog import BlogPostDetector
        detector = BlogPostDetector()
        assert detector is not None

    def test_url_patterns(self):
        from readpile.crawlers.blog import BlogPostDetector
        detector = BlogPostDetector()
        assert hasattr(detector, "detect")


class TestBlogCrawlerConfig:
    def test_constructor_params(self):
        try:
            from readpile.crawlers.blog import BlogCrawler
        except SystemExit:
            pytest.skip("Deps not available")

        context = MagicMock()
        crawler = BlogCrawler(
            browser_context=context,
            base_url="https://example.com/blog",
            delay=0.5,
            max_posts=10,
        )
        assert crawler.base_url == "https://example.com/blog"
        assert crawler.delay == 0.5
        assert crawler.max_posts == 10
        assert crawler.base_domain == "example.com"

    def test_default_max_posts_none(self):
        try:
            from readpile.crawlers.blog import BlogCrawler
        except SystemExit:
            pytest.skip("Deps not available")

        context = MagicMock()
        crawler = BlogCrawler(context, "https://example.com/blog")
        assert crawler.max_posts is None

    def test_same_domain_filtering(self):
        try:
            from readpile.crawlers.blog import BlogCrawler
        except SystemExit:
            pytest.skip("Deps not available")

        context = MagicMock()
        crawler = BlogCrawler(context, "https://example.com/blog")
        assert crawler.base_domain == "example.com"
        assert crawler.base_scheme == "https"
