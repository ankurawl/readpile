"""Source registry — reads/writes ~/.readpile/sources.toml."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import tomlkit

log = logging.getLogger("readpile.sync")


@dataclass
class Source:
    """A configured feed source."""

    name: str
    url: str
    kind: str  # rss, youtube, podcast
    synthesize: bool = True
    disabled: bool = False


class SourceRegistry:
    """Read/write ``~/.readpile/sources.toml`` with round-trip TOML preservation."""

    def __init__(self, sources_file: Path, lock_path: Path | None = None) -> None:
        self.sources_file = Path(sources_file).expanduser()
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

    def load(self) -> list[Source]:
        if not self.sources_file.exists():
            return []
        text = self.sources_file.read_text(encoding="utf-8")
        self._doc = tomlkit.parse(text)
        raw_sources = self._doc.get("sources", [])
        sources: list[Source] = []
        for s in raw_sources:
            sources.append(Source(
                name=s.get("name", ""),
                url=s.get("url", ""),
                kind=s.get("kind", "rss"),
                synthesize=s.get("synthesize", True),
                disabled=s.get("disabled", False),
            ))
        return sources

    def save(self) -> None:
        self._check_lock()
        if self._doc is None:
            self._doc = tomlkit.document()
        self.sources_file.parent.mkdir(parents=True, exist_ok=True)
        self.sources_file.write_text(tomlkit.dumps(self._doc), encoding="utf-8")

    def add(self, source: Source) -> None:
        self._check_lock()
        if self._doc is None:
            self.load()
        if self._doc is None:
            self._doc = tomlkit.document()

        sources = self._doc.get("sources")
        if sources is None:
            sources = tomlkit.aot()
            self._doc.add("sources", sources)

        item = tomlkit.table()
        item.add("name", source.name)
        item.add("url", source.url)
        item.add("kind", source.kind)
        if not source.synthesize:
            item.add("synthesize", False)
        if source.disabled:
            item.add("disabled", True)
        sources.append(item)
        self.save()

    def remove(self, name: str) -> None:
        self._check_lock()
        if self._doc is None:
            self.load()
        if self._doc is None:
            return
        sources = self._doc.get("sources", [])
        for i, s in enumerate(sources):
            if s.get("name") == name:
                del sources[i]
                self.save()
                return
        raise KeyError(f"Source not found: {name!r}")

    def enable(self, name: str) -> None:
        self._check_lock()
        if self._doc is None:
            self.load()
        if self._doc is None:
            return
        for s in self._doc.get("sources", []):
            if s.get("name") == name:
                if "disabled" in s:
                    del s["disabled"]
                self.save()
                return
        raise KeyError(f"Source not found: {name!r}")

    def disable(self, name: str) -> None:
        self._check_lock()
        if self._doc is None:
            self.load()
        if self._doc is None:
            return
        for s in self._doc.get("sources", []):
            if s.get("name") == name:
                s["disabled"] = True
                self.save()
                return
        raise KeyError(f"Source not found: {name!r}")

    def update_url(self, name: str, new_url: str) -> None:
        self._check_lock()
        if self._doc is None:
            self.load()
        if self._doc is None:
            return
        for s in self._doc.get("sources", []):
            if s.get("name") == name:
                s["url"] = new_url
                self.save()
                return
        raise KeyError(f"Source not found: {name!r}")
