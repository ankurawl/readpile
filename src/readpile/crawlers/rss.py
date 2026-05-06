"""RSS crawler — parse and enumerate entries from RSS/Atom feeds."""

from __future__ import annotations

import logging
from datetime import datetime
from time import mktime, struct_time

try:
    import feedparser
except ImportError:
    feedparser = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dependency guard
# ---------------------------------------------------------------------------


def _check_deps() -> None:
    """Verify feedparser is installed."""
    if feedparser is None:
        raise SystemExit(
            "RSS crawling requires feedparser. Install with:\n"
            "  pip install readpile\n"
            "  or: pip install feedparser\n"
        )


def crawl_rss(url: str, recent: int | None = None) -> list[str]:
    """Parse an RSS 2.0 or Atom feed and return entry URLs.

    For podcast feeds the audio enclosure URL is preferred over the entry
    link.  Entries are sorted by published date (newest first).  If
    *recent* is set only the N most recent entries are returned.

    Malformed feeds are handled gracefully: a warning is logged and an
    empty list is returned.
    """
    _check_deps()

    feed = feedparser.parse(url)

    if feed.bozo and not feed.entries:
        logger.warning(f"Malformed or empty feed at {url}: {feed.bozo_exception}")
        return []

    # Build (date, url) pairs so we can sort by date
    entries: list[tuple[datetime | None, str]] = []
    for entry in feed.entries:
        entry_url = _get_entry_url(entry)
        if not entry_url:
            continue
        entry_date = _get_entry_date(entry)
        entries.append((entry_date, entry_url))

    # Sort newest first.  Entries without a date go to the end.
    entries.sort(key=lambda pair: pair[0] or datetime.min, reverse=True)

    urls = [url for _, url in entries]

    if recent is not None:
        urls = urls[:recent]

    return urls


def _get_entry_url(entry: feedparser.FeedParserDict) -> str | None:
    """Extract the best URL from a feed entry.

    For podcast feeds (entries with an audio enclosure) the enclosure URL
    is returned.  Otherwise the entry ``link`` is used.
    """
    # Prefer audio enclosure for podcast feeds
    if _has_audio_enclosure(entry):
        for enc in entry.get("enclosures", []):
            enc_type = enc.get("type", "")
            if enc_type.startswith("audio/") or enc.get("href", "").endswith(
                (".mp3", ".m4a", ".ogg", ".wav")
            ):
                href = enc.get("href")
                if href:
                    return href

    # Fall back to the entry link
    link = entry.get("link")
    if link:
        return link

    return None


def _get_entry_date(entry: feedparser.FeedParserDict) -> datetime | None:
    """Parse the published or updated date from a feed entry.

    Returns ``None`` if no date information is available or the date
    cannot be parsed.
    """
    for field in ("published_parsed", "updated_parsed"):
        raw = entry.get(field)
        if isinstance(raw, struct_time):
            try:
                return datetime.fromtimestamp(mktime(raw))
            except (ValueError, OverflowError, OSError):
                continue
    return None


def _has_audio_enclosure(entry: feedparser.FeedParserDict) -> bool:
    """Return ``True`` if the entry contains at least one audio enclosure."""
    for enc in entry.get("enclosures", []):
        enc_type = enc.get("type", "")
        if enc_type.startswith("audio/"):
            return True
        href = enc.get("href", "")
        if href.endswith((".mp3", ".m4a", ".ogg", ".wav")):
            return True
    return False


def _get_audio_enclosure_url(entry: feedparser.FeedParserDict) -> str | None:
    """Return the URL of the first audio enclosure, or ``None``."""
    for enc in entry.get("enclosures", []):
        enc_type = enc.get("type", "")
        href = enc.get("href", "")
        if enc_type.startswith("audio/") or href.endswith(
            (".mp3", ".m4a", ".ogg", ".wav")
        ):
            if href:
                return href
    return None


def _strip_html(text: str) -> str:
    """Remove HTML tags from *text*."""
    import re
    return re.sub(r"<[^>]+>", "", text).strip()


def crawl_rss_detailed(
    url: str,
    recent: int | None = None,
    audio_only: bool = False,
) -> tuple[dict, list[dict]]:
    """Parse an RSS/Atom feed and return structured metadata for each entry.

    Returns ``(feed_info, entries)`` where *feed_info* contains feed-level
    metadata and *entries* is a list of dicts with per-entry metadata.

    When *audio_only* is ``True``, only entries with audio enclosures are
    returned (useful for isolating podcast episodes from mixed feeds).
    """
    _check_deps()

    feed = feedparser.parse(url)

    if feed.bozo and not feed.entries:
        logger.warning(f"Malformed or empty feed at {url}: {feed.bozo_exception}")
        return {"feed_title": None, "feed_description": None, "episode_count": 0}, []

    entries: list[tuple[datetime | None, dict]] = []
    for entry in feed.entries:
        is_audio = _has_audio_enclosure(entry)
        if audio_only and not is_audio:
            continue

        audio_url = _get_audio_enclosure_url(entry) if is_audio else None
        page_url = entry.get("link")

        entry_date = _get_entry_date(entry)
        date_str = entry_date.strftime("%Y-%m-%d") if entry_date else None

        summary = entry.get("summary", "")
        description = _strip_html(summary)[:300] if summary else None

        meta = {
            "title": entry.get("title", "Untitled"),
            "url": page_url or audio_url,
            "date": date_str,
            "author": entry.get("author"),
            "type": "audio" if is_audio else "article",
            "audio_url": audio_url,
            "duration": entry.get("itunes_duration"),
            "description": description,
        }
        entries.append((entry_date, meta))

    entries.sort(key=lambda pair: pair[0] or datetime.min, reverse=True)

    result = [meta for _, meta in entries]
    if recent is not None:
        result = result[:recent]

    feed_info = {
        "feed_title": feed.feed.get("title"),
        "feed_description": feed.feed.get("subtitle") or feed.feed.get("description"),
        "episode_count": len(result),
    }

    return feed_info, result
