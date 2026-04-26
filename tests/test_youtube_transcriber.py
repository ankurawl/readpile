from datetime import date
from unittest.mock import patch, MagicMock
from mediakit.transcribers.youtube import (
    get_youtube_metadata, get_youtube_transcript, transcribe_youtube,
    VideoNotFoundError, TranscriptNotAvailableError, _format_duration,
)
from mediakit.core.models import ContentType
import pytest

def test_format_duration_with_hours():
    assert _format_duration(3661) == "1:01:01"

def test_format_duration_minutes_only():
    assert _format_duration(125) == "2:05"

def test_format_duration_zero():
    assert _format_duration(0) == "0:00"

@patch("mediakit.transcribers.youtube.yt_dlp.YoutubeDL")
def test_get_metadata(mock_ydl_cls):
    mock_ydl = MagicMock()
    mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
    mock_ydl.extract_info.return_value = {
        "title": "Test Video",
        "channel": "Test Channel",
        "duration": 600,
        "upload_date": "20260425",
        "id": "abc123",
        "description": "A test video",
    }
    meta = get_youtube_metadata("https://youtube.com/watch?v=abc123")
    assert meta["title"] == "Test Video"
    assert meta["channel"] == "Test Channel"
    assert meta["duration"] == "10:00"
    assert meta["video_id"] == "abc123"

@patch("mediakit.transcribers.youtube.yt_dlp.YoutubeDL")
def test_get_metadata_not_found(mock_ydl_cls):
    import yt_dlp
    mock_ydl = MagicMock()
    mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
    mock_ydl.extract_info.side_effect = yt_dlp.utils.DownloadError("not found")
    with pytest.raises(VideoNotFoundError):
        get_youtube_metadata("https://youtube.com/watch?v=invalid")

@patch("mediakit.transcribers.youtube.YouTubeTranscriptApi")
def test_get_transcript(mock_api_cls):
    mock_api = MagicMock()
    mock_api_cls.return_value = mock_api

    mock_transcript = MagicMock()
    mock_segment = MagicMock()
    mock_segment.text = "Hello world"
    mock_transcript.fetch.return_value = [mock_segment] * 10

    mock_list = MagicMock()
    mock_list.find_transcript.return_value = mock_transcript
    mock_api.list.return_value = mock_list

    text = get_youtube_transcript("abc123", "en")
    assert "Hello world" in text
    assert len(text) > 0

@patch("mediakit.transcribers.youtube.get_youtube_transcript")
@patch("mediakit.transcribers.youtube.get_youtube_metadata")
def test_transcribe_youtube(mock_meta, mock_transcript):
    mock_meta.return_value = {
        "title": "Full Test", "channel": "Ch", "duration": "5:00",
        "upload_date": "20260101", "video_id": "xyz", "url": "https://youtube.com/watch?v=xyz",
        "description": "desc",
    }
    mock_transcript.return_value = "Transcript paragraph one.\n\nParagraph two."

    item = transcribe_youtube("https://youtube.com/watch?v=xyz")
    assert item.content_type == ContentType.youtube
    assert item.title == "Full Test"
    assert item.channel == "Ch"
    assert item.duration == "5:00"
    assert item.date == date(2026, 1, 1)
    assert "Transcript" in item.text
