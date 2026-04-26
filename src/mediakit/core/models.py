"""Data models — shared dataclasses and types."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class ContentType(Enum):
    """Supported content types."""

    article = "article"
    youtube = "youtube"
    audio = "audio"
    podcast = "podcast"
    webpage = "webpage"


@dataclass
class ContentItem:
    """A single piece of extracted content with metadata."""

    text: str
    title: str
    source_url: str
    content_type: ContentType
    date: date | None = None
    author: str | None = None
    tags: list[str] = field(default_factory=list)
    duration: str | None = None  # for audio/video
    channel: str | None = None  # for YouTube
    word_count: int = 0

    def __post_init__(self) -> None:
        if self.word_count == 0 and self.text:
            self.word_count = len(self.text.split())

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_yaml_header(self) -> str:
        """Generate a YAML front matter block from non-None/non-empty fields."""
        lines: list[str] = ["---"]

        # Always present
        lines.append(f'title: "{self.title}"')
        lines.append(f"source_url: {self.source_url}")
        lines.append(f"content_type: {self.content_type.value}")

        if self.date is not None:
            lines.append(f"date: {self.date.isoformat()}")

        if self.author is not None:
            lines.append(f'author: "{self.author}"')

        if self.tags:
            tag_str = ", ".join(self.tags)
            lines.append(f"tags: [{tag_str}]")

        if self.duration is not None:
            lines.append(f'duration: "{self.duration}"')

        if self.channel is not None:
            lines.append(f'channel: "{self.channel}"')

        if self.word_count:
            lines.append(f"word_count: {self.word_count}")

        lines.append("---")
        return "\n".join(lines) + "\n"

    def to_stdout(self) -> str:
        """Combine YAML front matter and body text for stdout output."""
        return self.to_yaml_header() + "\n" + self.text + "\n"

    # ------------------------------------------------------------------
    # Deserialization
    # ------------------------------------------------------------------

    @classmethod
    def from_stdin(cls, text: str) -> ContentItem:
        """Parse YAML front matter + body into a ContentItem.

        Expects text formatted as:
            ---
            key: value
            ...
            ---
            body text here
        """
        text = text.strip()

        # Split on the --- delimiters
        if not text.startswith("---"):
            raise ValueError("Input must start with '---' YAML front matter delimiter")

        # Find the second '---' delimiter
        second_delim = text.index("---", 3)
        yaml_block = text[3:second_delim].strip()
        body = text[second_delim + 3:].strip()

        # Parse YAML key-value lines
        meta: dict[str, str] = {}
        for line in yaml_block.splitlines():
            line = line.strip()
            if not line:
                continue
            match = re.match(r"^([a-z_]+):\s*(.*)$", line)
            if match:
                key = match.group(1)
                value = match.group(2).strip()
                meta[key] = value

        # Helper to unquote a string value
        def _unquote(s: str) -> str:
            if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
                return s[1:-1]
            return s

        # Helper to parse tags: [a, b, c]
        def _parse_tags(s: str) -> list[str]:
            s = s.strip()
            if s.startswith("[") and s.endswith("]"):
                inner = s[1:-1]
                if not inner.strip():
                    return []
                return [t.strip() for t in inner.split(",")]
            return []

        # Required fields
        title = _unquote(meta.get("title", ""))
        source_url = meta.get("source_url", "")
        content_type_str = meta.get("content_type", "")
        try:
            content_type = ContentType(content_type_str)
        except ValueError:
            raise ValueError(f"Unknown content_type: {content_type_str!r}")

        # Optional fields
        date_val: date | None = None
        if "date" in meta and meta["date"]:
            date_val = date.fromisoformat(meta["date"])

        author: str | None = None
        if "author" in meta and meta["author"]:
            author = _unquote(meta["author"])

        tags: list[str] = []
        if "tags" in meta and meta["tags"]:
            tags = _parse_tags(meta["tags"])

        duration: str | None = None
        if "duration" in meta and meta["duration"]:
            duration = _unquote(meta["duration"])

        channel: str | None = None
        if "channel" in meta and meta["channel"]:
            channel = _unquote(meta["channel"])

        word_count = int(meta.get("word_count", "0") or "0")

        return cls(
            text=body,
            title=title,
            source_url=source_url,
            content_type=content_type,
            date=date_val,
            author=author,
            tags=tags,
            duration=duration,
            channel=channel,
            word_count=word_count,
        )

    @classmethod
    def from_stdin_batch(cls, text: str) -> list[ContentItem]:
        """Parse multiple ContentItems separated by ---CONTENT_ITEM--- delimiters."""
        chunks = text.split("---CONTENT_ITEM---")
        items: list[ContentItem] = []
        for chunk in chunks:
            chunk = chunk.strip()
            if chunk:
                items.append(cls.from_stdin(chunk))
        return items

    @staticmethod
    def to_batch(items: list[ContentItem]) -> str:
        """Join multiple ContentItems with the batch delimiter."""
        return "\n---CONTENT_ITEM---\n\n".join(item.to_stdout() for item in items)
