"""Tests for mediakit.bot.telegram_formatter — Telegram message formatting."""

import pytest

from mediakit.bot.telegram_formatter import (
    TELEGRAM_MSG_LIMIT,
    create_summary_document,
    format_error_message,
    format_processing_status,
    format_summary_message,
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
def sample_summary():
    return (
        "## Summary\n"
        "This is a test summary about an interesting topic.\n\n"
        "## Key Takeaways\n"
        "- Point 1\n"
        "- Point 2\n"
        "- Point 3\n\n"
        "## Learnings\n"
        "- Learning 1\n"
        "- Learning 2"
    )


class TestFormatSummaryMessage:
    def test_detailed_style_includes_all_sections(self, sample_metadata, sample_summary):
        msg = format_summary_message(sample_metadata, sample_summary, style="detailed")
        assert "<b>Test Video Title</b>" in msg
        assert "Test Channel" in msg
        assert "10:30" in msg
        assert "Summary" in msg
        assert "Key Takeaways" in msg
        assert "Learnings" in msg

    def test_brief_style_only_key_takeaways(self, sample_metadata, sample_summary):
        msg = format_summary_message(sample_metadata, sample_summary, style="brief")
        assert "<b>Test Video Title</b>" in msg
        assert "Key Takeaways" in msg
        # The brief style should extract only the Key Takeaways section
        assert "Point 1" in msg

    def test_message_truncation(self, sample_metadata):
        # Create a summary that exceeds the Telegram limit
        long_summary = "## Summary\n" + ("A" * (TELEGRAM_MSG_LIMIT + 1000))
        msg = format_summary_message(sample_metadata, long_summary, style="detailed")
        assert len(msg) <= TELEGRAM_MSG_LIMIT
        assert "[Full summary attached as file]" in msg

    def test_includes_url(self, sample_metadata, sample_summary):
        msg = format_summary_message(sample_metadata, sample_summary)
        assert sample_metadata["url"] in msg

    def test_default_style_is_detailed(self, sample_metadata, sample_summary):
        msg = format_summary_message(sample_metadata, sample_summary)
        assert "Summary" in msg
        assert "Learnings" in msg

    def test_markdown_headings_to_html_bold(self, sample_metadata, sample_summary):
        msg = format_summary_message(sample_metadata, sample_summary, style="detailed")
        # ## headings should be converted to <b> tags
        assert "<b>Summary</b>" in msg or "<b>Key Takeaways</b>" in msg


class TestCreateSummaryDocument:
    def test_returns_bytes_and_filename(self, sample_metadata, sample_summary):
        doc_bytes, filename = create_summary_document(
            sample_metadata, sample_summary, "This is the transcript."
        )
        assert isinstance(doc_bytes, bytes)
        assert isinstance(filename, str)
        assert filename.endswith(".md")

    def test_document_contains_metadata(self, sample_metadata, sample_summary):
        doc_bytes, _ = create_summary_document(
            sample_metadata, sample_summary, "transcript text"
        )
        content = doc_bytes.decode("utf-8")
        assert "Test Video Title" in content
        assert "Test Channel" in content
        assert "10:30" in content

    def test_document_contains_summary_and_transcript(self, sample_metadata, sample_summary):
        transcript = "This is the full transcript."
        doc_bytes, _ = create_summary_document(
            sample_metadata, sample_summary, transcript
        )
        content = doc_bytes.decode("utf-8")
        assert sample_summary in content
        assert transcript in content

    def test_filename_contains_sanitized_title(self, sample_metadata, sample_summary):
        _, filename = create_summary_document(
            sample_metadata, sample_summary, "transcript"
        )
        # Filename should contain the date and a sanitized title
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
        assert format_processing_status("summarizing") == "Summarizing with LLM..."
        assert format_processing_status("formatting") == "Formatting output..."

    def test_unknown_step_falls_back(self):
        msg = format_processing_status("custom_step")
        assert msg == "custom_step..."
