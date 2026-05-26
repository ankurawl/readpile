"""Tests for readpile.sync.digest — DigestBuilder and DigestSender."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from readpile.sync.digest import DigestBuilder, DigestSender
from readpile.sync.state import SyncState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _item(
    title: str = "Test Article",
    url: str = "https://example.com/article",
    content_type: str = "article",
    word_count: int = 500,
    preview: str = "",
    source_path: str = "",
) -> dict:
    d: dict = {
        "title": title,
        "url": url,
        "content_type": content_type,
        "word_count": word_count,
        "source_path": source_path or f"sources/{title.lower().replace(' ', '-')}.md",
    }
    if preview:
        d["preview"] = preview
    return d


def _state(tmp_path: Path) -> SyncState:
    return SyncState(state_file=tmp_path / "state.json")


def _config(**overrides) -> dict:
    cfg: dict = {"sync": {"digest": {"smtp_host": "smtp.test.local", "smtp_port": 587, "from": "digest@test.local"}}}
    for k, v in overrides.items():
        cfg["sync"]["digest"][k] = v
    return cfg


# ---------------------------------------------------------------------------
# DigestBuilder
# ---------------------------------------------------------------------------


class TestDigestBuilderEmpty:
    """Zero items should produce empty body and no files."""

    def test_zero_items(self, tmp_path):
        state = _state(tmp_path)
        builder = DigestBuilder(_config())
        body, files = builder.build([], state)
        assert body == ""
        assert files == []


class TestDigestBuilderSingle:
    """One or two items produce a single digest.md file without LLM grouping."""

    def test_single_item(self, tmp_path):
        state = _state(tmp_path)
        builder = DigestBuilder(_config())
        body, files = builder.build([_item()], state)
        assert len(files) == 1
        assert files[0].name == "digest.md"
        assert files[0].exists()
        content = files[0].read_text()
        assert "Test Article" in content

    def test_two_items(self, tmp_path):
        state = _state(tmp_path)
        builder = DigestBuilder(_config())
        items = [_item(title="Article A"), _item(title="Article B")]
        body, files = builder.build(items, state)
        assert len(files) == 1
        assert files[0].name == "digest.md"


class TestDigestBuilderMultipleTopics:
    """Five items should use the LLM to group into topic files."""

    @patch("readpile.sync.llm.generate")
    def test_five_items_grouped(self, mock_generate, tmp_path):
        mock_generate.return_value = json.dumps({
            "AI Research": [1, 2],
            "Web Development": [3, 4],
            "Miscellaneous": [5],
        })
        state = _state(tmp_path)
        builder = DigestBuilder(_config())
        items = [_item(title=f"Article {i}") for i in range(1, 6)]
        body, files = builder.build(items, state)
        assert len(files) == 3
        filenames = {f.name for f in files}
        assert "ai-research.md" in filenames
        assert "web-development.md" in filenames
        assert "miscellaneous.md" in filenames
        for f in files:
            assert f.exists()

    @patch("readpile.sync.llm.generate")
    def test_max_topic_files_enforced(self, mock_generate, tmp_path):
        mock_generate.return_value = json.dumps({
            f"Topic {i}": [i] for i in range(1, 11)
        })
        state = _state(tmp_path)
        config = _config()
        config["sync"]["digest"]["max_topic_files"] = 3
        builder = DigestBuilder(config)
        items = [_item(title=f"Article {i}") for i in range(1, 11)]
        body, files = builder.build(items, state)
        assert len(files) <= 3


class TestDigestBuilderLLMFailure:
    """LLM failure should fall back to a flat list under 'All Items'."""

    @patch("readpile.sync.llm.generate", side_effect=RuntimeError("API down"))
    def test_fallback_flat_list(self, mock_generate, tmp_path):
        state = _state(tmp_path)
        builder = DigestBuilder(_config())
        items = [_item(title=f"Article {i}") for i in range(1, 6)]
        body, files = builder.build(items, state)
        assert len(files) == 1
        content = files[0].read_text()
        assert "All Items" in content


class TestDigestBuilderBody:
    """Verify numbered items, reply instructions, and config suggestions in the body."""

    def test_numbered_items_in_body(self, tmp_path):
        state = _state(tmp_path)
        builder = DigestBuilder(_config())
        items = [_item(title="First"), _item(title="Second")]
        body, _ = builder.build(items, state)
        assert "1. **First**" in body
        assert "2. **Second**" in body

    def test_reply_instructions_in_body(self, tmp_path):
        state = _state(tmp_path)
        builder = DigestBuilder(_config())
        body, _ = builder.build([_item()], state)
        assert "Reply to this email to control synthesis." in body
        assert "Synthesize items" in body
        assert "Skip item" in body

    def test_unknown_senders_listed(self, tmp_path):
        state = _state(tmp_path)
        builder = DigestBuilder(_config())
        body, _ = builder.build(
            [_item()],
            state,
            skipped_unknown_senders=["stranger@evil.com", "spam@junk.net"],
        )
        assert "2 emails from unknown senders skipped" in body
        assert "stranger@evil.com" in body
        assert "spam@junk.net" in body

    def test_errors_listed(self, tmp_path):
        state = _state(tmp_path)
        builder = DigestBuilder(_config())
        body, _ = builder.build(
            [_item()],
            state,
            errors=["Failed to scrape https://broken.com: timeout"],
        )
        assert "1 items failed" in body
        assert "https://broken.com" in body


class TestDigestHistory:
    """Digest state should be stored in SyncState with a rolling window."""

    def test_digest_state_stored(self, tmp_path):
        state = _state(tmp_path)
        builder = DigestBuilder(_config())
        builder.build([_item()], state)
        history = state.get_digest_history()
        assert len(history) == 1
        assert "readpile" in history[0]["subject"]
        assert "item_map" in history[0]
        assert "1" in history[0]["item_map"]

    def test_rolling_window_max_seven(self, tmp_path):
        state = _state(tmp_path)
        builder = DigestBuilder(_config())
        for i in range(10):
            builder.build([_item(title=f"Item {i}")], state)
        history = state.get_digest_history()
        assert len(history) == 7


# ---------------------------------------------------------------------------
# DigestSender
# ---------------------------------------------------------------------------


class TestDigestSenderSmtp:
    """DigestSender.send() should send email via SMTP when password is set."""

    @patch("readpile.sync.digest.DigestSender._send_pending")
    @patch("readpile.sync.digest.smtplib.SMTP")
    def test_email_sent_via_smtp(self, mock_smtp_cls, mock_send_pending, tmp_path):
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        sender = DigestSender(_config(smtp_password="secret123"))
        att_file = tmp_path / "digest.md"
        att_file.write_text("# Digest content")

        sender.send(
            subject="readpile digest",
            body="Test body",
            attachments=[att_file],
            to="user@example.com",
        )

        mock_smtp_cls.assert_called_once_with("smtp.test.local", 587)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("digest@test.local", "secret123")
        mock_server.send_message.assert_called_once()
        mock_send_pending.assert_called_once()

    @patch("readpile.sync.digest.DigestSender._send_pending")
    @patch("readpile.sync.digest.smtplib.SMTP")
    def test_attachments_included(self, mock_smtp_cls, mock_send_pending, tmp_path):
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        sender = DigestSender(_config(smtp_password="secret123"))
        files = []
        for name in ["topic-a.md", "topic-b.md"]:
            f = tmp_path / name
            f.write_text(f"# {name}")
            files.append(f)

        sender.send("subject", "body", files, "user@example.com")

        sent_msg = mock_server.send_message.call_args[0][0]
        payloads = sent_msg.get_payload()
        # First payload is the text body, rest are attachments
        assert len(payloads) == 3  # 1 text + 2 attachments


class TestDigestSenderSmtpFailure:
    """SMTP failure should save the digest to the pending directory."""

    @patch("readpile.sync.digest.DigestSender._send_pending")
    @patch("readpile.sync.digest.smtplib.SMTP")
    def test_smtp_failure_saves_pending(
        self, mock_smtp_cls, mock_send_pending, tmp_path, monkeypatch
    ):
        mock_server = MagicMock()
        mock_server.send_message.side_effect = ConnectionError("SMTP down")
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        pending_dir = tmp_path / "pending-digest"
        monkeypatch.setattr(
            Path,
            "expanduser",
            lambda self: tmp_path / self.name if "pending" in str(self) else self,
        )

        sender = DigestSender(_config(smtp_password="secret123"))

        att = tmp_path / "digest.md"
        att.write_text("# Content")

        # Patch _save_pending to use our tmp_path
        original_save = sender._save_pending

        def patched_save(subject, body, attachments):
            from datetime import date

            today_dir = pending_dir / date.today().isoformat()
            today_dir.mkdir(parents=True, exist_ok=True)
            (today_dir / "subject.txt").write_text(subject, encoding="utf-8")
            (today_dir / "body.md").write_text(body, encoding="utf-8")
            for a in attachments:
                import shutil

                shutil.copy2(a, today_dir / a.name)

        sender._save_pending = patched_save
        sender.send("Test Subject", "Test Body", [att], "user@example.com")

        assert pending_dir.exists()
        day_dirs = list(pending_dir.iterdir())
        assert len(day_dirs) == 1
        assert (day_dirs[0] / "subject.txt").read_text() == "Test Subject"
        assert (day_dirs[0] / "body.md").read_text() == "Test Body"
        assert (day_dirs[0] / "digest.md").exists()
        mock_send_pending.assert_not_called()  # Should not be called on failure


class TestDigestSenderNoPassword:
    """Missing SMTP password should save to pending, not crash."""

    def test_no_password_saves_pending(self, tmp_path, monkeypatch):
        sender = DigestSender(_config())
        save_called = {"called": False}

        def mock_save(subject, body, attachments):
            save_called["called"] = True

        sender._save_pending = mock_save

        att = tmp_path / "digest.md"
        att.write_text("# Content")

        sender.send("Subject", "Body", [att], "user@example.com")
        assert save_called["called"]
