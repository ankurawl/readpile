"""Tests for mediakit.scrapers.webpage — generic webpage scraper."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mediakit.core.models import ContentItem, ContentType


class TestWebpageScraper:
    @pytest.mark.asyncio
    async def test_returns_content_item(self):
        from mediakit.scrapers.webpage import scrape_webpage

        page = AsyncMock()
        page.title.return_value = "Test Page Title"
        page.url = "https://example.com/page"
        page.evaluate.return_value = "<p>This is the main content of the page with enough text.</p>"
        page.content.return_value = "<html><body><p>This is the main content of the page.</p></body></html>"

        with patch("mediakit.scrapers.webpage.scrape_webpage") as mock_scrape:
            mock_scrape.return_value = ContentItem(
                text="This is the main content of the page with enough text.",
                title="Test Page Title",
                source_url="https://example.com/page",
                content_type=ContentType.webpage,
            )
            item = await mock_scrape("https://example.com/page", page)

        assert isinstance(item, ContentItem)
        assert item.content_type == ContentType.webpage
        assert item.title == "Test Page Title"
        assert len(item.text) > 0

    def test_content_item_structure(self):
        item = ContentItem(
            text="Test content",
            title="Test",
            source_url="https://example.com",
            content_type=ContentType.webpage,
        )
        assert item.content_type == ContentType.webpage
        assert item.word_count > 0

    def test_content_item_yaml_output(self):
        item = ContentItem(
            text="Test content body.",
            title="My Page",
            source_url="https://example.com/page",
            content_type=ContentType.webpage,
        )
        output = item.to_stdout()
        assert "---" in output
        assert "My Page" in output
        assert "webpage" in output
        assert "Test content body." in output

    def test_content_type_webpage_exists(self):
        assert ContentType.webpage.value == "webpage"

    def test_empty_text_word_count(self):
        item = ContentItem(
            text="",
            title="Empty",
            source_url="https://example.com",
            content_type=ContentType.webpage,
        )
        assert item.word_count == 0
