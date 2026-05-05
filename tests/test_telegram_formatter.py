"""Tests for readpile.bot.telegram_formatter — Telegram message formatting."""

import pytest

from readpile.bot.telegram_formatter import (
    TELEGRAM_MSG_LIMIT,
    create_content_document,
    format_error_message,
    format_processing_status,
    format_content_message,
)


@pytest.fixture
def sample_metadata():
    return {
        "title": "Test Video Title",
        "channel": "Test Channel",
        "duration": "10:30",
        "url": "https://www.youtube.com/watch?v=abc123",
    }


@pytest.fixture
def sample_content():
    return (
        "## Introduction\n"
        "This is a test article about an interesting topic.\n\n"
        "## Key Points\n"
        "- Point 1\n"
        "- Point 2\n"
        "- Point 3\n\n"
        "## Conclusion\n"
        "- Learning 1\n"
        "- Learning 2"
    )


class TestFormatContentMessage:
    def test_detailed_style_includes_all_content(self, sample_metadata, sample_content):
        msg = format_content_message(sample_metadata, sample_content, style="detailed")
        assert "<b>Test Video Title</b>" in msg
        assert "Test Channel" in msg
        assert "10:30" in msg
        assert "Introduction" in msg
        assert "Key Points" in msg
        assert "Conclusion" in msg

    def test_brief_style_truncates(self, sample_metadata):
        long_content = "A" * 1000
        msg = format_content_message(sample_metadata, long_content, style="brief")
        assert "<b>Test Video Title</b>" in msg
        assert "..." in msg
        assert len(msg) < len(long_content)

    def test_brief_style_short_content_no_ellipsis(self, sample_metadata):
        short_content = "Short text."
        msg = format_content_message(sample_metadata, short_content, style="brief")
        assert "Short text." in msg
        assert "..." not in msg

    def test_message_truncation(self, sample_metadata):
        long_content = "A" * (TELEGRAM_MSG_LIMIT + 1000)
        msg = format_content_message(sample_metadata, long_content, style="detailed")
        assert len(msg) <= TELEGRAM_MSG_LIMIT
        assert "[Full content attached as file]" in msg

    def test_includes_url(self, sample_metadata, sample_content):
        msg = format_content_message(sample_metadata, sample_content)
        assert sample_metadata["url"] in msg

    def test_default_style_is_detailed(self, sample_metadata, sample_content):
        msg = format_content_message(sample_metadata, sample_content)
        assert "Introduction" in msg
        assert "Conclusion" in msg

    def test_markdown_headings_to_html_bold(self, sample_metadata, sample_content):
        msg = format_content_message(sample_metadata, sample_content, style="detailed")
        assert "<b>Introduction</b>" in msg or "<b>Key Points</b>" in msg


class TestCreateContentDocument:
    def test_returns_bytes_and_filename(self, sample_metadata, sample_content):
        doc_bytes, filename = create_content_document(sample_metadata, sample_content)
        assert isinstance(doc_bytes, bytes)
        assert isinstance(filename, str)
        assert filename.endswith(".md")

    def test_document_contains_metadata(self, sample_metadata, sample_content):
        doc_bytes, _ = create_content_document(sample_metadata, sample_content)
        content = doc_bytes.decode("utf-8")
        assert "Test Video Title" in content
        assert "Test Channel" in content
        assert "10:30" in content

    def test_document_contains_content(self, sample_metadata, sample_content):
        doc_bytes, _ = create_content_document(sample_metadata, sample_content)
        decoded = doc_bytes.decode("utf-8")
        assert sample_content in decoded
        assert "## Full Transcript" not in decoded

    def test_filename_contains_sanitized_title(self, sample_metadata, sample_content):
        _, filename = create_content_document(sample_metadata, sample_content)
        assert "test-video-title" in filename


class TestFormatErrorMessage:
    def test_wraps_in_bold_header(self):
        msg = format_error_message("Something went wrong")
        assert "<b>Error</b>" in msg
        assert "Something went wrong" in msg

    def test_preserves_error_text(self):
        error = "Video not found. Check the URL"
        msg = format_error_message(error)
        assert error in msg


class TestFormatProcessingStatus:
    def test_known_steps(self):
        assert format_processing_status("detecting") == "Detecting content type..."
        assert format_processing_status("metadata") == "Fetching metadata..."
        assert format_processing_status("transcript") == "Extracting transcript..."
        assert format_processing_status("scraping") == "Scraping article content..."
        assert format_processing_status("downloading") == "Downloading audio..."
        assert format_processing_status("transcribing") == "Transcribing audio..."
        assert format_processing_status("formatting") == "Formatting output..."

    def test_summarizing_step_removed(self):
        msg = format_processing_status("summarizing")
        assert msg == "summarizing..."

    def test_unknown_step_falls_back(self):
        msg = format_processing_status("custom_step")
        assert msg == "custom_step..."
