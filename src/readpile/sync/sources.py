"""Feed registry — reads/writes ~/.readpile/feeds.toml."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import tomlkit

from readpile.sync.urls import normalize_url

log = logging.getLogger("readpile.sync")


@dataclass
class Feed:
    """A configured feed subscription."""

    name: str
    url: str
    kind: str  # rss, youtube, podcast
    synthesize: bool = True
    disabled: bool = False


class FeedRegistry:
    """Read/write ``~/.readpile/feeds.toml`` with round-trip TOML preservation."""

    def __init__(self, feeds_file: Path, lock_path: Path | None = None) -> None:
        self.feeds_file = Path(feeds_file).expanduser()
        self.lock_path = Path(lock_path).expanduser() if lock_path else None
        self._doc: tomlkit.TOMLDocument | None = None

    def _check_lock(self) -> None:
        if self.lock_path and self.lock_path.exists():
            text = self.lock_path.read_text().strip()
            parts = text.split("\n", 1)
            pid_str = parts[0] if parts else ""
            try:
                import os
                pid = int(pid_str)
                if pid != os.getpid():
                    os.kill(pid, 0)
                    raise RuntimeError(
                        f"Another readpile process is running (PID {pid})"
                    )
            except (ValueError, ProcessLookupError, OSError):
                pass

    def load(self) -> list[Feed]:
        if not self.feeds_file.exists():
            self._doc = tomlkit.document()
            return []
        text = self.feeds_file.read_text(encoding="utf-8")
        self._doc = tomlkit.parse(text)
        raw_feeds = self._doc.get("feeds", [])
        
        seen_urls = set()
        feeds: list[Feed] = []
        indices_to_remove = []

        for i, s in enumerate(raw_feeds):
            url = s.get("url", "")
            norm_url = normalize_url(url)
            if norm_url in seen_urls:
                indices_to_remove.append(i)
                continue
            
            seen_urls.add(norm_url)
            feeds.append(Feed(
                name=s.get("name", ""),
                url=url,
                kind=s.get("kind", "rss"),
                synthesize=s.get("synthesize", True),
                disabled=s.get("disabled", False),
            ))

        if indices_to_remove:
            log.info("Removing %d duplicate feeds from registry", len(indices_to_remove))
            for i in reversed(indices_to_remove):
                del raw_feeds[i]
            self.save()

        return feeds

    def save(self) -> None:
        self._check_lock()
        if self._doc is None:
            self._doc = tomlkit.document()
        self.feeds_file.parent.mkdir(parents=True, exist_ok=True)
        self.feeds_file.write_text(tomlkit.dumps(self._doc), encoding="utf-8")

    def has_url(self, url: str) -> bool:
        """Check if a normalized URL is already in the registry."""
        if self._doc is None:
            self.load()
        norm_url = normalize_url(url)
        for s in self._doc.get("feeds", []):
            if normalize_url(s.get("url", "")) == norm_url:
                return True
        return False

    def add(self, feed: Feed) -> str:
        """Add a feed or update metadata if it exists. Returns 'added', 'updated', or 'unchanged'."""
        self._check_lock()
        if self._doc is None:
            self.load()
        
        norm_url = normalize_url(feed.url)
        sources = self._doc.get("feeds")
        
        if sources is not None:
            for s in sources:
                if normalize_url(s.get("url", "")) == norm_url:
                    changed = False
                    if feed.name and s.get("name") != feed.name:
                        s["name"] = feed.name
                        changed = True
                    if feed.kind and s.get("kind") != feed.kind:
                        s["kind"] = feed.kind
                        changed = True
                    
                    if changed:
                        self.save()
                        return "updated"
                    return "unchanged"

        if sources is None:
            sources = tomlkit.aot()
            self._doc.add("feeds", sources)

        item = tomlkit.table()
        item.add("name", feed.name)
        item.add("url", feed.url)
        item.add("kind", feed.kind)
        if not feed.synthesize:
            item.add("synthesize", False)
        if feed.disabled:
            item.add("disabled", True)
        sources.append(item)
        self.save()
        return "added"

    def remove(self, name: str) -> None:
        """Remove feed by name (backward compatibility)."""
        self._check_lock()
        if self._doc is None:
            self.load()
        sources = self._doc.get("feeds", [])
        for i, s in enumerate(sources):
            if s.get("name") == name:
                del sources[i]
                self.save()
                return
        raise KeyError(f"Feed not found: {name!r}")

    def remove_by_url(self, url: str) -> None:
        """Remove a feed by its URL."""
        self._check_lock()
        if self._doc is None:
            self.load()
            
        norm_url = normalize_url(url)
        sources = self._doc.get("feeds", [])
        for i, s in enumerate(sources):
            if normalize_url(s.get("url", "")) == norm_url:
                del sources[i]
                self.save()
                return
        raise KeyError(f"Feed not found with URL: {url!r}")

    def enable(self, name: str) -> None:
        self._check_lock()
        if self._doc is None:
            self.load()
        if self._doc is None:
            return
        for s in self._doc.get("feeds", []):
            if s.get("name") == name:
                if "disabled" in s:
                    del s["disabled"]
                self.save()
                return
        raise KeyError(f"Feed not found: {name!r}")

    def disable(self, name: str) -> None:
        self._check_lock()
        if self._doc is None:
            self.load()
        if self._doc is None:
            return
        for s in self._doc.get("feeds", []):
            if s.get("name") == name:
                s["disabled"] = True
                self.save()
                return
        raise KeyError(f"Feed not found: {name!r}")

    def update_url(self, name: str, new_url: str) -> None:
        self._check_lock()
        if self._doc is None:
            self.load()
        if self._doc is None:
            return
        for s in self._doc.get("feeds", []):
            if s.get("name") == name:
                s["url"] = new_url
                self.save()
                return
        raise KeyError(f"Feed not found: {name!r}")
