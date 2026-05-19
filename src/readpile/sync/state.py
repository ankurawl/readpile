"""Sync state — JSON-backed tracking, lock file, signal handlers."""

from __future__ import annotations

import atexit
import json
import logging
import os
import signal
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger("readpile.sync")

_STATE_VERSION = 1
_MAX_SEEN_IDS = 1000
_MAX_SEEN_URLS_PER_FEED = 500
_MAX_SAVED_URLS = 5000
_LOCK_STALE_HOURS = 4

_EMPTY_STATE: dict = {
    "version": _STATE_VERSION,
    "last_sync": None,
    "email": {"seen_ids": []},
    "feeds": {},
    "saved_urls": [],
    "synthesis": {
        "pending": {},
        "synthesized": {},
        "skipped": {},
        "failed": {},
    },
    "digest": {"history": []},
}


class SyncState:
    """Load/save/commit sync state, manage lock file and signal handlers."""

    def __init__(self, state_file: Path, wiki_dir: Path | None = None) -> None:
        self.state_file = Path(state_file).expanduser()
        self.wiki_dir = Path(wiki_dir).expanduser() if wiki_dir else None
        self._data: dict = {}
        self._shutting_down = False
        self._lock_path: Path | None = None
        self._prev_sigterm = None
        self._prev_sigint = None
        self.load()

    @property
    def shutting_down(self) -> bool:
        return self._shutting_down

    def load(self) -> None:
        if self.state_file.exists():
            try:
                text = self.state_file.read_text(encoding="utf-8")
                self._data = json.loads(text)
                self._migrate()
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                log.warning("State file corrupted (%s), starting fresh", exc)
                self._data = json.loads(json.dumps(_EMPTY_STATE))
                self._recover_saved_urls()
        else:
            self._data = json.loads(json.dumps(_EMPTY_STATE))

    def _migrate(self) -> None:
        version = self._data.get("version", 0)
        if version > _STATE_VERSION:
            raise RuntimeError(
                f"State file version {version} is newer than supported ({_STATE_VERSION}). "
                "Upgrade readpile or delete the state file."
            )
        for key in _EMPTY_STATE:
            if key not in self._data:
                self._data[key] = json.loads(json.dumps(_EMPTY_STATE[key]))
        synth = self._data.setdefault("synthesis", {})
        for sub_key in ("pending", "synthesized", "skipped", "failed"):
            synth.setdefault(sub_key, {})
        self._data.setdefault("digest", {}).setdefault("history", [])
        self._data["version"] = _STATE_VERSION

    def _recover_saved_urls(self) -> None:
        if self.wiki_dir is None:
            return
        sources_dir = self.wiki_dir / "sources"
        if not sources_dir.exists():
            return
        import re
        url_pattern = re.compile(r"^source_url:\s*(.+)$", re.MULTILINE)
        recovered = []
        for path in sources_dir.glob("*.md"):
            try:
                text = path.read_text(encoding="utf-8")
                match = url_pattern.search(text)
                if match:
                    from readpile.sync.urls import normalize_url
                    recovered.append(normalize_url(match.group(1).strip()))
            except Exception:
                continue
        if recovered:
            self._data["saved_urls"] = recovered
            log.info("Recovered %d saved URLs from wiki sources", len(recovered))

    # ------------------------------------------------------------------
    # Email tracking
    # ------------------------------------------------------------------

    def is_email_seen(self, msg_id: str) -> bool:
        return msg_id in self._data["email"]["seen_ids"]

    def mark_email_seen(self, msg_id: str) -> None:
        seen = self._data["email"]["seen_ids"]
        if msg_id not in seen:
            seen.append(msg_id)

    # ------------------------------------------------------------------
    # Feed tracking
    # ------------------------------------------------------------------

    def _feed_entry(self, feed_key: str) -> dict:
        feeds = self._data["feeds"]
        if feed_key not in feeds:
            feeds[feed_key] = {"seen_urls": [], "consecutive_failures": 0}
        return feeds[feed_key]

    def is_url_seen(self, url: str, feed_key: str) -> bool:
        entry = self._feed_entry(feed_key)
        return url in entry["seen_urls"]

    def mark_url_seen(self, url: str, feed_key: str) -> None:
        entry = self._feed_entry(feed_key)
        if url not in entry["seen_urls"]:
            entry["seen_urls"].append(url)

    def get_feed_seen_urls(self, feed_key: str) -> list[str]:
        return self._feed_entry(feed_key).get("seen_urls", [])

    def get_consecutive_failures(self, feed_key: str) -> int:
        return self._feed_entry(feed_key).get("consecutive_failures", 0)

    def increment_failure(self, feed_key: str) -> int:
        entry = self._feed_entry(feed_key)
        entry["consecutive_failures"] = entry.get("consecutive_failures", 0) + 1
        return entry["consecutive_failures"]

    def reset_failures(self, feed_key: str) -> None:
        self._feed_entry(feed_key)["consecutive_failures"] = 0

    # ------------------------------------------------------------------
    # Global URL dedup
    # ------------------------------------------------------------------

    def is_saved_url(self, url: str) -> bool:
        from readpile.sync.urls import normalize_url
        return normalize_url(url) in self._data["saved_urls"]

    def mark_saved_url(self, url: str) -> None:
        from readpile.sync.urls import normalize_url
        normalized = normalize_url(url)
        if normalized not in self._data["saved_urls"]:
            self._data["saved_urls"].append(normalized)

    def remove_saved_url(self, url: str) -> None:
        from readpile.sync.urls import normalize_url
        normalized = normalize_url(url)
        try:
            self._data["saved_urls"].remove(normalized)
        except ValueError:
            pass

    # ------------------------------------------------------------------
    # Synthesis tracking
    # ------------------------------------------------------------------

    def mark_pending(self, source_path: str, timestamp: str | None = None) -> None:
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        self._data["synthesis"]["pending"][source_path] = ts

    def mark_synthesized(self, source_path: str) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        self._data["synthesis"]["pending"].pop(source_path, None)
        self._data["synthesis"]["failed"].pop(source_path, None)
        self._data["synthesis"]["synthesized"][source_path] = ts

    def mark_skipped(self, source_path: str) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        self._data["synthesis"]["pending"].pop(source_path, None)
        self._data["synthesis"]["skipped"][source_path] = ts

    def mark_synthesis_failed(self, source_path: str, error: str) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        self._data["synthesis"]["pending"].pop(source_path, None)
        self._data["synthesis"]["failed"][source_path] = {
            "timestamp": ts, "error": error,
        }

    def get_pending(self) -> dict[str, str]:
        return dict(self._data["synthesis"]["pending"])

    def get_synthesized(self) -> dict[str, str]:
        return dict(self._data["synthesis"]["synthesized"])

    def get_skipped(self) -> dict[str, str]:
        return dict(self._data["synthesis"]["skipped"])

    def get_failed(self) -> dict:
        return dict(self._data["synthesis"]["failed"])

    # ------------------------------------------------------------------
    # Digest tracking
    # ------------------------------------------------------------------

    def set_digest_state(
        self, subject: str, message_id: str, item_map: dict[str, str],
    ) -> None:
        from datetime import date
        entry = {
            "subject": subject,
            "message_id": message_id,
            "date": date.today().isoformat(),
            "item_map": item_map,
        }
        history = self._data["digest"]["history"]
        history.append(entry)
        if len(history) > 7:
            self._data["digest"]["history"] = history[-7:]

    def get_digest_history(self) -> list[dict]:
        return list(self._data["digest"]["history"])

    # ------------------------------------------------------------------
    # Commit (atomic write)
    # ------------------------------------------------------------------

    def commit(self) -> None:
        self._data["last_sync"] = datetime.now(timezone.utc).isoformat()
        self._evict()
        self._cleanup_old_synthesis()

        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        bak_path = self.state_file.with_suffix(".json.bak")
        if self.state_file.exists():
            try:
                import shutil
                shutil.copy2(self.state_file, bak_path)
            except Exception:
                pass

        state_dir = self.state_file.parent
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", dir=state_dir, delete=False, encoding="utf-8",
        ) as tmp:
            json.dump(self._data, tmp, indent=2)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        tmp_path.rename(self.state_file)

    def _evict(self) -> None:
        seen_ids = self._data["email"]["seen_ids"]
        if len(seen_ids) > _MAX_SEEN_IDS:
            self._data["email"]["seen_ids"] = seen_ids[-_MAX_SEEN_IDS:]

        for feed_key, entry in self._data["feeds"].items():
            seen = entry.get("seen_urls", [])
            if len(seen) > _MAX_SEEN_URLS_PER_FEED:
                entry["seen_urls"] = seen[-_MAX_SEEN_URLS_PER_FEED:]

        saved = self._data["saved_urls"]
        if len(saved) > _MAX_SAVED_URLS:
            self._data["saved_urls"] = saved[-_MAX_SAVED_URLS:]

    def _cleanup_old_synthesis(self) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        synth = self._data["synthesis"]
        for bucket in ("pending", "synthesized", "skipped"):
            synth[bucket] = {
                k: v for k, v in synth[bucket].items()
                if v > cutoff
            }
        synth["failed"] = {
            k: v for k, v in synth["failed"].items()
            if isinstance(v, dict) and v.get("timestamp", "") > cutoff
        }

    # ------------------------------------------------------------------
    # Reset helpers
    # ------------------------------------------------------------------

    def reset_feeds(self) -> None:
        self._data["feeds"] = {}

    def reset_all(self) -> None:
        self._data = json.loads(json.dumps(_EMPTY_STATE))

    # ------------------------------------------------------------------
    # Lock file
    # ------------------------------------------------------------------

    def acquire_lock(self, lock_path: Path) -> None:
        lock_path = Path(lock_path).expanduser()
        self._lock_path = lock_path

        if lock_path.exists():
            text = lock_path.read_text().strip()
            lines = text.split("\n", 1)
            pid_str = lines[0] if lines else ""
            ts_str = lines[1] if len(lines) > 1 else ""
            try:
                pid = int(pid_str)
                stale_by_age = False
                if ts_str:
                    try:
                        lock_time = datetime.fromisoformat(ts_str)
                        age = datetime.now(timezone.utc) - lock_time
                        stale_by_age = age > timedelta(hours=_LOCK_STALE_HOURS)
                    except ValueError:
                        stale_by_age = True

                if stale_by_age:
                    log.warning("Stale lock file (age > %dh), overriding", _LOCK_STALE_HOURS)
                else:
                    os.kill(pid, 0)
                    raise RuntimeError(
                        f"Another readpile process is running (PID {pid})"
                    )
            except ProcessLookupError:
                log.warning("Stale lock file (PID %s dead), overriding", pid_str)
            except ValueError:
                log.warning("Corrupt lock file, overriding")

        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(
            f"{os.getpid()}\n{datetime.now(timezone.utc).isoformat()}\n"
        )

        atexit.register(self.release_lock)
        self._prev_sigterm = signal.getsignal(signal.SIGTERM)
        self._prev_sigint = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def release_lock(self) -> None:
        if self._lock_path and self._lock_path.exists():
            try:
                text = self._lock_path.read_text().strip()
                pid_str = text.split("\n", 1)[0]
                if pid_str == str(os.getpid()):
                    self._lock_path.unlink()
            except Exception:
                pass

    def _signal_handler(self, signum: int, frame) -> None:
        self._shutting_down = True
        try:
            self.commit()
        except Exception:
            pass
        self.release_lock()
        if signum == signal.SIGTERM and callable(self._prev_sigterm):
            self._prev_sigterm(signum, frame)
        elif signum == signal.SIGINT and callable(self._prev_sigint):
            self._prev_sigint(signum, frame)
        raise SystemExit(128 + signum)
