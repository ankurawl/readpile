"""Archiver — filename generation, sanitization, and saving ContentItems to disk.

Merges patterns from blog-scraper's PostWriter (underscore slugs, dedup)
and yt-summarizer's formatter (hyphen slugs, date prefix).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mediakit.core.models import ContentItem


# ---------------------------------------------------------------------------
# Standalone helpers
# ---------------------------------------------------------------------------


def sanitize_filename(title: str, max_length: int = 80) -> str:
    """Convert *title* to a filesystem-safe, hyphen-separated slug.

    Steps:
      1. Lowercase.
      2. Strip non-alphanumeric characters (keep spaces and hyphens).
      3. Replace spaces and underscores with hyphens.
      4. Collapse consecutive hyphens.
      5. Strip leading/trailing hyphens.
      6. Truncate to *max_length* without leaving a trailing hyphen.
    """
    name = title.lower()
    # Remove everything that isn't alphanumeric, space, or hyphen
    name = re.sub(r"[^a-z0-9 \-]", "", name)
    # Spaces and underscores → hyphen
    name = re.sub(r"[\s_]+", "-", name)
    # Collapse runs of hyphens
    name = re.sub(r"-+", "-", name)
    # Strip edges
    name = name.strip("-")
    # Truncate and clean trailing hyphen
    name = name[:max_length].rstrip("-")
    return name


def generate_filename(
    item: ContentItem,
    date_format: str = "YYYY-MM-DD",
) -> str:
    """Build a Markdown filename from a :class:`ContentItem`.

    Format: ``{date}_{title-slug}.md``

    * If ``item.date`` is set, format it as *YYYY-MM-DD*; otherwise fall
      back to today's date (UTC).
    * The title slug is produced by :func:`sanitize_filename`.
    """
    # Resolve date string
    if item.date is not None:
        if isinstance(item.date, str):
            date_str = item.date  # already formatted
        else:
            # datetime-like
            fmt = date_format.replace("YYYY", "%Y").replace("MM", "%m").replace("DD", "%d")
            date_str = item.date.strftime(fmt)
    else:
        fmt = date_format.replace("YYYY", "%Y").replace("MM", "%m").replace("DD", "%d")
        date_str = datetime.now(tz=timezone.utc).strftime(fmt)

    slug = sanitize_filename(item.title)
    return f"{date_str}_{slug}.md"


# ---------------------------------------------------------------------------
# Archiver class
# ---------------------------------------------------------------------------


class Archiver:
    """Saves :class:`ContentItem` objects to disk with deduplication.

    Parameters
    ----------
    output_dir:
        Directory where files are written.  Created automatically if it
        does not exist.
    date_format:
        strftime-compatible format string used for the date prefix
        (default ``"YYYY-MM-DD"``).
    """

    def __init__(self, output_dir: str | Path, date_format: str = "YYYY-MM-DD") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.date_format = date_format
        self._used_names: set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self, item: ContentItem) -> Path:
        """Generate a unique filename, write *item* to disk, and return the path.

        The file content is obtained via ``item.to_stdout()``.
        """
        filename = generate_filename(item, date_format=self.date_format)
        filename = self._deduplicate(filename)
        filepath = self.output_dir / filename
        filepath.write_text(item.to_stdout(), encoding="utf-8")
        return filepath

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _deduplicate(self, filename: str) -> str:
        """Append ``_2``, ``_3``, ... before ``.md`` if *filename* is already used."""
        if filename not in self._used_names:
            self._used_names.add(filename)
            return filename

        base, _, ext = filename.rpartition(".")
        counter = 2
        while True:
            candidate = f"{base}_{counter}.{ext}"
            if candidate not in self._used_names:
                self._used_names.add(candidate)
                return candidate
            counter += 1
