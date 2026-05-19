"""Tests for readpile.sync.state — SyncState load/save/commit, locking, eviction."""

from __future__ import annotations

import json
import os
import signal
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from readpile.sync.state import SyncState, _STATE_VERSION


# --- Load / Save / Commit round-trip ---


class TestLoadSaveCommit:
    def test_fresh_state_creates_defaults(self, tmp_path):
        state_file = tmp_path / "state.json"
        state = SyncState(state_file)
        assert not state.is_email_seen("any-id")
        assert not state.is_saved_url("https://example.com")

    def test_commit_creates_file(self, tmp_path):
        state_file = tmp_path / "state.json"
        state = SyncState(state_file)
        state.mark_email_seen("msg1")
        state.commit()
        assert state_file.exists()

    def test_round_trip(self, tmp_path):
        state_file = tmp_path / "state.json"
        state = SyncState(state_file)
        state.mark_email_seen("msg-abc")
        state.mark_saved_url("https://example.com/article")
        state.mark_pending("sources/post.md")
        state.commit()

        state2 = SyncState(state_file)
        assert state2.is_email_seen("msg-abc")
        assert state2.is_saved_url("https://example.com/article")
        assert "sources/post.md" in state2.get_pending()

    def test_last_sync_set_on_commit(self, tmp_path):
        state_file = tmp_path / "state.json"
        state = SyncState(state_file)
        state.commit()

        data = json.loads(state_file.read_text())
        assert data["last_sync"] is not None


# --- Email tracking ---


class TestEmailTracking:
    def test_mark_and_check(self, tmp_path):
        state = SyncState(tmp_path / "state.json")
        assert not state.is_email_seen("msg-1")
        state.mark_email_seen("msg-1")
        assert state.is_email_seen("msg-1")

    def test_duplicate_mark_is_idempotent(self, tmp_path):
        state = SyncState(tmp_path / "state.json")
        state.mark_email_seen("msg-1")
        state.mark_email_seen("msg-1")
        # Should only appear once in the list
        data = state._data["email"]["seen_ids"]
        assert data.count("msg-1") == 1

    def test_eviction_caps_at_1000(self, tmp_path):
        state = SyncState(tmp_path / "state.json")
        for i in range(1200):
            state.mark_email_seen(f"msg-{i}")
        state.commit()

        state2 = SyncState(tmp_path / "state.json")
        seen = state2._data["email"]["seen_ids"]
        assert len(seen) == 1000
        # Oldest should be evicted, newest kept
        assert "msg-0" not in seen
        assert "msg-1199" in seen


# --- Feed tracking ---


class TestFeedTracking:
    def test_mark_and_check_url(self, tmp_path):
        state = SyncState(tmp_path / "state.json")
        assert not state.is_url_seen("https://a.com/1", "feed-a")
        state.mark_url_seen("https://a.com/1", "feed-a")
        assert state.is_url_seen("https://a.com/1", "feed-a")

    def test_feeds_are_independent(self, tmp_path):
        state = SyncState(tmp_path / "state.json")
        state.mark_url_seen("https://a.com/1", "feed-a")
        assert not state.is_url_seen("https://a.com/1", "feed-b")

    def test_eviction_caps_at_500_per_feed(self, tmp_path):
        state = SyncState(tmp_path / "state.json")
        for i in range(600):
            state.mark_url_seen(f"https://example.com/{i}", "big-feed")
        state.commit()

        state2 = SyncState(tmp_path / "state.json")
        seen = state2._data["feeds"]["big-feed"]["seen_urls"]
        assert len(seen) == 500
        # Oldest evicted
        assert "https://example.com/0" not in seen
        assert "https://example.com/599" in seen

    def test_consecutive_failures(self, tmp_path):
        state = SyncState(tmp_path / "state.json")
        assert state.get_consecutive_failures("feed-x") == 0
        state.increment_failure("feed-x")
        assert state.get_consecutive_failures("feed-x") == 1
        state.increment_failure("feed-x")
        assert state.get_consecutive_failures("feed-x") == 2
        state.reset_failures("feed-x")
        assert state.get_consecutive_failures("feed-x") == 0


# --- Saved URLs dedup ---


class TestSavedUrls:
    def test_normalizes_urls(self, tmp_path):
        state = SyncState(tmp_path / "state.json")
        state.mark_saved_url("https://www.example.com/post?utm_source=rss")
        assert state.is_saved_url("https://example.com/post")

    def test_dedup_prevents_duplicates(self, tmp_path):
        state = SyncState(tmp_path / "state.json")
        state.mark_saved_url("https://example.com/post")
        state.mark_saved_url("https://example.com/post")
        assert state._data["saved_urls"].count("https://example.com/post") == 1

    def test_remove_saved_url(self, tmp_path):
        state = SyncState(tmp_path / "state.json")
        state.mark_saved_url("https://example.com/post")
        assert state.is_saved_url("https://example.com/post")
        state.remove_saved_url("https://example.com/post")
        assert not state.is_saved_url("https://example.com/post")

    def test_eviction_caps_at_5000_oldest_first(self, tmp_path):
        state = SyncState(tmp_path / "state.json")
        for i in range(5100):
            state.mark_saved_url(f"https://example.com/{i}")
        state.commit()

        state2 = SyncState(tmp_path / "state.json")
        saved = state2._data["saved_urls"]
        assert len(saved) == 5000
        # Oldest evicted (kept the last 5000)
        assert "https://example.com/0" not in saved
        assert "https://example.com/5099" in saved


# --- Synthesis lifecycle ---


class TestSynthesisLifecycle:
    def test_pending_to_synthesized(self, tmp_path):
        state = SyncState(tmp_path / "state.json")
        state.mark_pending("sources/a.md")
        assert "sources/a.md" in state.get_pending()
        state.mark_synthesized("sources/a.md")
        assert "sources/a.md" not in state.get_pending()
        assert "sources/a.md" in state.get_synthesized()

    def test_pending_to_skipped(self, tmp_path):
        state = SyncState(tmp_path / "state.json")
        state.mark_pending("sources/b.md")
        state.mark_skipped("sources/b.md")
        assert "sources/b.md" not in state.get_pending()
        assert "sources/b.md" in state.get_skipped()

    def test_pending_to_failed(self, tmp_path):
        state = SyncState(tmp_path / "state.json")
        state.mark_pending("sources/c.md")
        state.mark_synthesis_failed("sources/c.md", "LLM timeout")
        assert "sources/c.md" not in state.get_pending()
        failed = state.get_failed()
        assert "sources/c.md" in failed
        assert failed["sources/c.md"]["error"] == "LLM timeout"


# --- 90-day cleanup ---


class TestCleanup:
    def test_removes_old_entries(self, tmp_path):
        state = SyncState(tmp_path / "state.json")
        old_ts = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        recent_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()

        state._data["synthesis"]["pending"]["old-source.md"] = old_ts
        state._data["synthesis"]["pending"]["recent-source.md"] = recent_ts
        state._data["synthesis"]["synthesized"]["old-synth.md"] = old_ts
        state._data["synthesis"]["skipped"]["old-skip.md"] = old_ts
        state._data["synthesis"]["failed"]["old-fail.md"] = {
            "timestamp": old_ts, "error": "err",
        }

        state.commit()

        state2 = SyncState(tmp_path / "state.json")
        assert "old-source.md" not in state2.get_pending()
        assert "recent-source.md" in state2.get_pending()
        assert "old-synth.md" not in state2.get_synthesized()
        assert "old-skip.md" not in state2.get_skipped()
        assert "old-fail.md" not in state2.get_failed()


# --- Digest history rolling window ---


class TestDigestHistory:
    def test_stores_digest_entry(self, tmp_path):
        state = SyncState(tmp_path / "state.json")
        state.set_digest_state("Digest 1", "msg-d1", {"url1": "source1"})
        history = state.get_digest_history()
        assert len(history) == 1
        assert history[0]["subject"] == "Digest 1"

    def test_rolling_window_caps_at_7(self, tmp_path):
        state = SyncState(tmp_path / "state.json")
        for i in range(10):
            state.set_digest_state(f"Digest {i}", f"msg-{i}", {})
        history = state.get_digest_history()
        assert len(history) == 7
        # Oldest evicted
        assert history[0]["subject"] == "Digest 3"
        assert history[-1]["subject"] == "Digest 9"


# --- Atomic write ---


class TestAtomicWrite:
    def test_commit_uses_tmp_file_pattern(self, tmp_path):
        state_file = tmp_path / "state.json"
        state = SyncState(state_file)
        state.mark_email_seen("msg-1")
        state.commit()

        # The final file should exist and be valid JSON
        assert state_file.exists()
        data = json.loads(state_file.read_text())
        assert "msg-1" in data["email"]["seen_ids"]


# --- State backup rotation ---


class TestBackupRotation:
    def test_bak_file_created_on_commit(self, tmp_path):
        state_file = tmp_path / "state.json"

        # First commit creates the file
        state = SyncState(state_file)
        state.mark_email_seen("original")
        state.commit()

        # Second commit should back up the first
        state2 = SyncState(state_file)
        state2.mark_email_seen("updated")
        state2.commit()

        bak_path = state_file.with_suffix(".json.bak")
        assert bak_path.exists()
        bak_data = json.loads(bak_path.read_text())
        assert "original" in bak_data["email"]["seen_ids"]


# --- Version migration ---


class TestVersionMigration:
    def test_old_version_auto_migrates(self, tmp_path):
        state_file = tmp_path / "state.json"
        # Write a v0 state with missing keys
        old_state = {
            "version": 0,
            "last_sync": None,
            "email": {"seen_ids": ["old-msg"]},
            "feeds": {},
            "saved_urls": [],
        }
        state_file.write_text(json.dumps(old_state))

        state = SyncState(state_file)
        # Should have migrated — old data kept, new keys filled in
        assert state.is_email_seen("old-msg")
        assert state._data["version"] == _STATE_VERSION
        assert "synthesis" in state._data
        assert "digest" in state._data

    def test_newer_version_raises(self, tmp_path):
        state_file = tmp_path / "state.json"
        future_state = {"version": _STATE_VERSION + 10, "last_sync": None}
        state_file.write_text(json.dumps(future_state))

        with pytest.raises(RuntimeError, match="newer than supported"):
            SyncState(state_file)


# --- Lock file ---


class TestLockFile:
    def test_acquire_and_release(self, tmp_path):
        state = SyncState(tmp_path / "state.json")
        lock_path = tmp_path / "sync.lock"
        state.acquire_lock(lock_path)

        assert lock_path.exists()
        text = lock_path.read_text().strip()
        pid_str, ts_str = text.split("\n")
        assert int(pid_str) == os.getpid()
        # Timestamp should parse
        datetime.fromisoformat(ts_str)

        state.release_lock()
        assert not lock_path.exists()

    def test_stale_lock_dead_pid_recovered(self, tmp_path):
        lock_path = tmp_path / "sync.lock"
        # Write lock with a PID that definitely doesn't exist
        lock_path.write_text("999999999\n2026-01-01T00:00:00+00:00\n")

        state = SyncState(tmp_path / "state.json")
        # Should not raise — dead PID means stale lock recovered
        state.acquire_lock(lock_path)
        assert lock_path.exists()
        text = lock_path.read_text().strip()
        assert text.startswith(str(os.getpid()))
        state.release_lock()

    def test_stale_lock_old_age_recovered(self, tmp_path):
        lock_path = tmp_path / "sync.lock"
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        # Use current PID so os.kill(pid, 0) would succeed
        lock_path.write_text(f"{os.getpid()}\n{old_ts}\n")

        state = SyncState(tmp_path / "state.json")
        # Should not raise — lock is old enough to be considered stale
        state.acquire_lock(lock_path)
        state.release_lock()

    def test_live_lock_raises(self, tmp_path):
        lock_path = tmp_path / "sync.lock"
        # Use current PID with recent timestamp
        recent_ts = datetime.now(timezone.utc).isoformat()
        lock_path.write_text(f"{os.getpid()}\n{recent_ts}\n")

        state = SyncState(tmp_path / "state.json")
        with pytest.raises(RuntimeError, match="Another readpile process"):
            state.acquire_lock(lock_path)

    def test_corrupt_lock_file_overridden(self, tmp_path):
        lock_path = tmp_path / "sync.lock"
        lock_path.write_text("not-a-valid-lock-file")

        state = SyncState(tmp_path / "state.json")
        # Should not raise — corrupt lock is overridden
        state.acquire_lock(lock_path)
        state.release_lock()


# --- State file corruption recovery ---


class TestCorruptionRecovery:
    def test_corrupted_json_starts_fresh(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text("{invalid json content!!!")

        state = SyncState(state_file)
        # Should start fresh without raising
        assert not state.is_email_seen("anything")

    def test_corrupted_json_with_wiki_recovery(self, tmp_path):
        state_file = tmp_path / "state.json"
        wiki_dir = tmp_path / "wiki"
        sources_dir = wiki_dir / "sources"
        sources_dir.mkdir(parents=True)

        # Create a source file with a URL
        source_file = sources_dir / "2026-01-01_article.md"
        source_file.write_text(
            "---\ntitle: Test\nsource_url: https://example.com/recovered\n---\nContent"
        )

        state_file.write_text("corrupt!!!")
        state = SyncState(state_file, wiki_dir=wiki_dir)
        assert state.is_saved_url("https://example.com/recovered")


# --- Reset helpers ---


class TestResetHelpers:
    def test_reset_feeds(self, tmp_path):
        state = SyncState(tmp_path / "state.json")
        state.mark_url_seen("https://a.com/1", "feed-a")
        state.mark_url_seen("https://b.com/1", "feed-b")
        assert state.is_url_seen("https://a.com/1", "feed-a")

        state.reset_feeds()
        assert not state.is_url_seen("https://a.com/1", "feed-a")
        assert not state.is_url_seen("https://b.com/1", "feed-b")

    def test_reset_all(self, tmp_path):
        state = SyncState(tmp_path / "state.json")
        state.mark_email_seen("msg-1")
        state.mark_saved_url("https://example.com/1")
        state.mark_url_seen("https://a.com/1", "feed-a")
        state.mark_pending("sources/x.md")

        state.reset_all()
        assert not state.is_email_seen("msg-1")
        assert not state.is_saved_url("https://example.com/1")
        assert not state.is_url_seen("https://a.com/1", "feed-a")
        assert state.get_pending() == {}
