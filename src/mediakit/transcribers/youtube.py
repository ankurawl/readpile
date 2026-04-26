"""YouTube transcriber — fetch metadata and transcripts from YouTube videos."""

from __future__ import annotations

from datetime import date

try:
    import yt_dlp
except ImportError:
    yt_dlp = None  # type: ignore[assignment]

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import (
        NoTranscriptFound,
        TranscriptsDisabled,
        VideoUnavailable,
    )
except ImportError:
    YouTubeTranscriptApi = None  # type: ignore[assignment,misc]
    NoTranscriptFound = None  # type: ignore[assignment,misc]
    TranscriptsDisabled = None  # type: ignore[assignment,misc]
    VideoUnavailable = None  # type: ignore[assignment,misc]

from mediakit.core.models import ContentItem, ContentType


# ---------------------------------------------------------------------------
# Dependency guard
# ---------------------------------------------------------------------------


def _check_deps() -> None:
    """Verify YouTube transcription dependencies are installed."""
    missing: list[str] = []
    if YouTubeTranscriptApi is None:
        missing.append("youtube-transcript-api")
    if yt_dlp is None:
        missing.append("yt-dlp")
    if missing:
        raise SystemExit(
            f"YouTube transcription requires: {', '.join(missing)}.\n"
            "Install with:\n"
            "  pip install mediakit\n"
            f"  or: pip install {' '.join(missing)}\n"
        )


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class VideoNotFoundError(Exception):
    """Raised when a YouTube video cannot be found or accessed."""


class TranscriptNotAvailableError(Exception):
    """Raised when no usable transcript exists for a video."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_duration(seconds: int) -> str:
    """Format a duration in seconds into a human-readable string.

    Returns ``"H:MM:SS"`` when *seconds* >= 3600, otherwise ``"M:SS"``.
    """
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_youtube_metadata(url: str) -> dict:
    """Fetch metadata for a YouTube video.

    Parameters
    ----------
    url:
        Full YouTube URL (e.g. ``https://www.youtube.com/watch?v=...``).

    Returns
    -------
    dict
        Keys: ``title``, ``channel``, ``duration``, ``upload_date``,
        ``video_id``, ``url``, ``description``.

    Raises
    ------
    VideoNotFoundError
        If the video cannot be found or the URL is invalid.
    """
    _check_deps()

    ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError:
        raise VideoNotFoundError("Video not found. Check the URL")

    if info is None:
        raise VideoNotFoundError("Video not found. Check the URL")

    duration_secs = info.get("duration") or 0
    return {
        "title": info.get("title", ""),
        "channel": info.get("channel") or info.get("uploader", ""),
        "duration": _format_duration(duration_secs),
        "upload_date": info.get("upload_date", ""),
        "video_id": info.get("id", ""),
        "url": url,
        "description": info.get("description", ""),
    }


def get_youtube_transcript(video_id: str, language: str = "en") -> str:
    """Fetch the transcript for a YouTube video and return it as text.

    Transcript lines are grouped into paragraphs of roughly five lines each,
    separated by blank lines.

    Parameters
    ----------
    video_id:
        The YouTube video ID (the ``v`` query-param value).
    language:
        BCP-47 language code for the desired transcript (default ``"en"``).

    Returns
    -------
    str
        The full transcript text with paragraph breaks.

    Raises
    ------
    TranscriptNotAvailableError
        If transcripts are disabled, the video is unavailable, or no
        transcript exists in the requested language.
    """
    _check_deps()

    ytt = YouTubeTranscriptApi()
    try:
        transcript_list = ytt.list(video_id)
    except TranscriptsDisabled:
        raise TranscriptNotAvailableError(
            "Transcripts are disabled for this video."
        )
    except VideoUnavailable:
        raise TranscriptNotAvailableError(
            "No transcript available for this video."
        )

    try:
        transcript = transcript_list.find_transcript([language])
    except NoTranscriptFound:
        available = [t.language_code for t in transcript_list]
        raise TranscriptNotAvailableError(
            f"No transcript in '{language}'. Available: {', '.join(available)}"
        )

    segments = transcript.fetch()
    lines = [segment.text for segment in segments]

    # Group into paragraphs every ~5 lines
    paragraphs: list[str] = []
    chunk: list[str] = []
    for line in lines:
        chunk.append(line)
        if len(chunk) >= 5:
            paragraphs.append(" ".join(chunk))
            chunk = []
    if chunk:
        paragraphs.append(" ".join(chunk))

    return "\n\n".join(paragraphs)


def transcribe_youtube(url: str, language: str = "en") -> ContentItem:
    """Fetch metadata and transcript for a YouTube video.

    This is the main entry point that combines :func:`get_youtube_metadata`
    and :func:`get_youtube_transcript` into a single :class:`ContentItem`.

    Parameters
    ----------
    url:
        Full YouTube URL.
    language:
        BCP-47 language code for the transcript (default ``"en"``).

    Returns
    -------
    ContentItem
        A populated content item with the transcript text and video metadata.

    Raises
    ------
    VideoNotFoundError
        If the video cannot be found.
    TranscriptNotAvailableError
        If no usable transcript is available.
    """
    _check_deps()
    metadata = get_youtube_metadata(url)
    transcript = get_youtube_transcript(metadata["video_id"], language)

    # Parse upload_date from YYYYMMDD to a date object
    upload_date: date | None = None
    raw_date = metadata.get("upload_date", "")
    if raw_date and len(raw_date) == 8:
        try:
            upload_date = date(
                year=int(raw_date[:4]),
                month=int(raw_date[4:6]),
                day=int(raw_date[6:8]),
            )
        except ValueError:
            upload_date = None

    return ContentItem(
        content_type=ContentType.youtube,
        text=transcript,
        title=metadata["title"],
        source_url=url,
        date=upload_date,
        channel=metadata["channel"],
        duration=metadata["duration"],
    )
