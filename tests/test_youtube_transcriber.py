from datetime import date
from unittest.mock import patch, MagicMock
from readpile.transcribers.youtube import (
    get_youtube_metadata, get_youtube_transcript, transcribe_youtube,
    VideoNotFoundError, TranscriptNotAvailableError, _format_duration,
    _parse_vtt, _group_into_paragraphs,
)
from readpile.core.models import ContentType
import pytest

def test_format_duration_with_hours():
    assert _format_duration(3661) == "1:01:01"

def test_format_duration_minutes_only():
    assert _format_duration(125) == "2:05"

def test_format_duration_zero():
    assert _format_duration(0) == "0:00"

@patch("readpile.transcribers.youtube.yt_dlp.YoutubeDL")
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

@patch("readpile.transcribers.youtube.yt_dlp.YoutubeDL")
def test_get_metadata_not_found(mock_ydl_cls):
    import yt_dlp
    mock_ydl = MagicMock()
    mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
    mock_ydl.extract_info.side_effect = yt_dlp.utils.DownloadError("not found")
    with pytest.raises(VideoNotFoundError):
        get_youtube_metadata("https://youtube.com/watch?v=invalid")

@patch("readpile.transcribers.youtube.YouTubeTranscriptApi")
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

@patch("readpile.transcribers.youtube.get_youtube_transcript")
@patch("readpile.transcribers.youtube.get_youtube_metadata")
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


def test_parse_vtt_basic():
    vtt = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:05.000
Hello world

00:00:05.000 --> 00:00:10.000
This is a test

00:00:10.000 --> 00:00:15.000
Of the VTT parser
"""
    result = _parse_vtt(vtt)
    assert "Hello world" in result
    assert "This is a test" in result
    assert "VTT parser" in result
    assert "WEBVTT" not in result
    assert "-->" not in result


def test_parse_vtt_strips_html_tags():
    vtt = """WEBVTT

00:00:00.000 --> 00:00:05.000
<c.colorE5E5E5>Hello</c> <c.colorCCCCCC>world</c>
"""
    result = _parse_vtt(vtt)
    assert "Hello world" in result
    assert "<c." not in result


def test_parse_vtt_deduplicates_lines():
    vtt = """WEBVTT

00:00:00.000 --> 00:00:05.000
Same line

00:00:05.000 --> 00:00:10.000
Same line

00:00:10.000 --> 00:00:15.000
Different line
"""
    result = _parse_vtt(vtt)
    assert result.count("Same line") == 1
    assert "Different line" in result


def test_group_into_paragraphs():
    lines = [f"Line {i}" for i in range(12)]
    result = _group_into_paragraphs(lines)
    paragraphs = result.split("\n\n")
    assert len(paragraphs) == 3
    assert "Line 0" in paragraphs[0]
    assert "Line 5" in paragraphs[1]
    assert "Line 10" in paragraphs[2]


@patch("readpile.transcribers.youtube.YouTubeTranscriptApi")
def test_get_transcript_ip_blocked_falls_back_to_ytdlp(mock_api_cls):
    """When youtube-transcript-api raises IpBlocked, falls back to yt-dlp."""
    from youtube_transcript_api._errors import IpBlocked

    mock_api = MagicMock()
    mock_api_cls.return_value = mock_api
    mock_api.list.side_effect = IpBlocked("abc123")

    with patch(
        "readpile.transcribers.youtube._get_transcript_via_ytdlp",
        return_value="Fallback transcript text",
    ) as mock_fallback:
        result = get_youtube_transcript("abc123", "en")
        assert result == "Fallback transcript text"
        mock_fallback.assert_called_once_with("abc123", "en")
