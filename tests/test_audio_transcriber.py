"""Tests for mediakit.transcribers.audio — audio transcription."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from mediakit.core.models import ContentItem, ContentType


@pytest.mark.audio
class TestAudioTranscriberImports:
    def test_check_ffmpeg(self):
        from mediakit.transcribers.audio import _check_ffmpeg
        try:
            _check_ffmpeg()
        except SystemExit:
            pytest.skip("ffmpeg not installed")

    def test_check_whisper_deps(self):
        from mediakit.transcribers.audio import _check_whisper_deps
        try:
            _check_whisper_deps()
        except SystemExit:
            pytest.skip("Whisper not installed")


@pytest.mark.audio
class TestTimestampFormatting:
    def test_format_seconds_to_timestamp(self):
        from mediakit.transcribers.audio import _format_timestamp
        assert _format_timestamp(0) == "[00:00:00]"
        assert _format_timestamp(65) == "[00:01:05]"
        assert _format_timestamp(3661) == "[01:01:01]"

    def test_format_large_timestamp(self):
        from mediakit.transcribers.audio import _format_timestamp
        result = _format_timestamp(7200)
        assert result == "[02:00:00]"


@pytest.mark.audio
class TestAudioContentItem:
    def test_audio_content_type(self):
        item = ContentItem(
            text="[00:00] Hello world",
            title="Test Audio",
            source_url="https://example.com/audio.mp3",
            content_type=ContentType.audio,
            duration="5:30",
        )
        assert item.content_type == ContentType.audio
        assert item.duration == "5:30"
        assert item.word_count > 0

    def test_audio_yaml_output(self):
        item = ContentItem(
            text="Transcript text",
            title="Podcast Episode",
            source_url="https://example.com/ep1.mp3",
            content_type=ContentType.audio,
            channel="My Podcast",
            duration="45:00",
        )
        output = item.to_stdout()
        assert "audio" in output
        assert "Podcast Episode" in output
        assert "45:00" in output
        assert "My Podcast" in output


@pytest.mark.audio
class TestDiarizationNormalization:
    def test_content_type_audio_exists(self):
        assert ContentType.audio.value == "audio"

    def test_content_type_podcast_exists(self):
        assert ContentType.podcast.value == "podcast"
