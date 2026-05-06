"""Content detector — identify content type from URLs or file paths.

Auto-detects URL/source types for routing to the correct processing brick.
"""

import os
import re
from enum import Enum
from urllib.parse import urlparse, parse_qs


class URLType(Enum):
    """Supported source types for media processing."""

    youtube = "youtube"
    video = "video"
    rss = "rss"
    audio_file = "audio_file"
    local_file = "local_file"
    blog = "blog"
    website = "website"


# ---------------------------------------------------------------------------
# Extension sets
# ---------------------------------------------------------------------------

_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".wma"}
_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm"}

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

_YOUTUBE_RE = re.compile(
    r"(youtube\.com/(watch|shorts|live)|youtu\.be/|youtube\.com/playlist)"
)

_YOUTUBE_ID_PATTERNS = [
    # youtube.com/watch?v=ID
    re.compile(r"(?:youtube\.com/watch)"),
    # youtu.be/ID
    re.compile(r"youtu\.be/(?P<id>[A-Za-z0-9_-]{11})"),
    # youtube.com/shorts/ID
    re.compile(r"youtube\.com/shorts/(?P<id>[A-Za-z0-9_-]{11})"),
    # youtube.com/live/ID
    re.compile(r"youtube\.com/live/(?P<id>[A-Za-z0-9_-]{11})"),
]

_RSS_PATH_SEGMENTS = {"/feed", "/rss", "/atom.xml"}
_RSS_EXTENSIONS = {".xml", ".rss", ".atom"}

_VIDEO_HOST_RE = re.compile(r"(vimeo\.com|loom\.com)")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_url_type(source: str) -> URLType:
    """Detect the type of a media source.

    Detection priority (first match wins):

    1. **Local file** — path exists on disk or has no ``://`` scheme.
       - Audio extensions → ``audio_file``
       - Video extensions → ``video``
       - Everything else  → ``local_file``
    2. **YouTube** — recognised YouTube URL patterns → ``youtube``
    3. **Audio/Video URL** — URL ending with audio/video extension,
       or Vimeo/Loom host → ``audio_file`` / ``video``
    4. **RSS / Atom feed** — feed-like URL suffix or path → ``rss``
    5. **Default** → ``blog`` (most URLs are articles; the scraper handles it)
    """

    # ------------------------------------------------------------------
    # 1. Local file
    # ------------------------------------------------------------------
    if os.path.exists(source) or "://" not in source:
        ext = os.path.splitext(source)[1].lower()
        if ext in _AUDIO_EXTENSIONS:
            return URLType.audio_file
        if ext in _VIDEO_EXTENSIONS:
            return URLType.video
        return URLType.local_file

    # ------------------------------------------------------------------
    # 2. YouTube
    # ------------------------------------------------------------------
    if _YOUTUBE_RE.search(source):
        return URLType.youtube

    # ------------------------------------------------------------------
    # 3. Audio/Video URL (check before RSS path segments so that
    #    URLs like /feed/podcast/episode.mp3 are detected as audio)
    # ------------------------------------------------------------------
    parsed = urlparse(source)
    path_lower = parsed.path.lower()
    url_ext = os.path.splitext(path_lower)[1]

    if url_ext in _AUDIO_EXTENSIONS:
        return URLType.audio_file

    if _VIDEO_HOST_RE.search(parsed.netloc):
        return URLType.video

    if url_ext in _VIDEO_EXTENSIONS:
        return URLType.video

    # ------------------------------------------------------------------
    # 4. RSS / Atom feed
    # ------------------------------------------------------------------
    if os.path.splitext(path_lower)[1] in _RSS_EXTENSIONS:
        return URLType.rss

    for segment in _RSS_PATH_SEGMENTS:
        if segment in path_lower:
            return URLType.rss

    # ------------------------------------------------------------------
    # 5. Default → blog
    # ------------------------------------------------------------------
    return URLType.blog


def extract_youtube_video_id(url: str) -> str | None:
    """Extract a YouTube video ID from a URL.

    Supported formats::

        https://www.youtube.com/watch?v=dQw4w9WgXcQ
        https://youtu.be/dQw4w9WgXcQ
        https://www.youtube.com/shorts/dQw4w9WgXcQ
        https://www.youtube.com/live/dQw4w9WgXcQ

    Returns the 11-character video ID, or ``None`` if the URL does not
    match any known YouTube pattern.
    """

    # youtube.com/watch?v=ID — the ID lives in the query string
    parsed = urlparse(url)
    if "youtube.com" in parsed.netloc and parsed.path == "/watch":
        qs = parse_qs(parsed.query)
        v = qs.get("v")
        if v:
            return v[0]

    # youtu.be/ID
    if "youtu.be" in parsed.netloc:
        # Path is /ID — strip the leading slash
        video_id = parsed.path.lstrip("/").split("/")[0]
        if video_id:
            return video_id

    # youtube.com/shorts/ID  or  youtube.com/live/ID
    match = re.search(
        r"youtube\.com/(?:shorts|live)/([A-Za-z0-9_-]+)", url
    )
    if match:
        return match.group(1)

    return None
