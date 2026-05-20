"""Tests for readpile.sync.reply — ReplyProcessor action parsing and conflict resolution."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from readpile.sync.email.base import EmailMessage, EmailProvider
from readpile.sync.reply import (
    AddFeedAction,
    RemoveFeedAction,
    ReplyProcessor,
    SkipAction,
    SynthesizeAction,
)
from readpile.sync.state import SyncState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _msg(
    *,
    sender: str = "user@example.com",
    subject: str = "Re: readpile — 2026-05-19 (3 new items)",
    text_body: str = "",
    headers: dict[str, str] | None = None,
    message_id: str = "<reply-001>",
    minutes_ago: int = 5,
) -> EmailMessage:
    return EmailMessage(
        message_id=message_id,
        subject=subject,
        sender=sender,
        date=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
        text_body=text_body,
        headers=headers or {},
    )


def _config(to: str = "user@example.com") -> dict:
    return {"sync": {"digest": {"to": to}}}


def _state_with_digest(tmp_path, *, subject: str = "readpile — 2026-05-19 (3 new items)", message_id: str = "digest_2026-05-19") -> SyncState:
    state = SyncState(state_file=tmp_path / "state.json")
    item_map = {
        "1": "sources/article-one.md",
        "2": "sources/article-two.md",
        "3": "sources/article-three.md",
    }
    state.set_digest_state(subject, message_id, item_map)
    return state


def _mock_provider(messages: list[EmailMessage]) -> EmailProvider:
    provider = AsyncMock(spec=EmailProvider)
    provider.fetch_messages = AsyncMock(return_value=messages)
    return provider


# ---------------------------------------------------------------------------
# No reply → empty actions
# ---------------------------------------------------------------------------


class TestNoReply:
    """When there are no reply messages, no LLM call should be made."""

    @pytest.mark.asyncio
    async def test_no_messages_returns_empty(self, tmp_path):
        state = _state_with_digest(tmp_path)
        provider = _mock_provider([])
        processor = ReplyProcessor(_config())
        actions = await processor.process(provider, state)
        assert actions == []

    @pytest.mark.asyncio
    async def test_no_digest_history_returns_empty(self, tmp_path):
        state = SyncState(state_file=tmp_path / "state.json")
        provider = _mock_provider([_msg(text_body="synthesize 1")])
        processor = ReplyProcessor(_config())
        actions = await processor.process(provider, state)
        assert actions == []

    @pytest.mark.asyncio
    async def test_unrelated_message_ignored(self, tmp_path):
        state = _state_with_digest(tmp_path)
        msg = _msg(
            sender="user@example.com",
            subject="Totally unrelated subject",
            text_body="hey there",
        )
        provider = _mock_provider([msg])
        processor = ReplyProcessor(_config())
        actions = await processor.process(provider, state)
        assert actions == []


# ---------------------------------------------------------------------------
# Simple reply parsing
# ---------------------------------------------------------------------------


class TestSimpleReply:
    """A reply like 'synthesize 1, 3' should produce a SynthesizeAction with correct paths."""

    @pytest.mark.asyncio
    @patch("readpile.sync.llm.generate")
    async def test_synthesize_reply(self, mock_generate, tmp_path):
        mock_generate.return_value = json.dumps([
            {"type": "synthesize", "items": [1, 3]},
        ])
        state = _state_with_digest(tmp_path)
        msg = _msg(
            sender="user@example.com",
            subject="Re: readpile — 2026-05-19 (3 new items)",
            text_body="Synthesize items 1 and 3",
        )
        provider = _mock_provider([msg])
        processor = ReplyProcessor(_config())
        actions = await processor.process(provider, state)

        assert len(actions) == 1
        assert isinstance(actions[0], SynthesizeAction)
        assert sorted(actions[0].source_paths) == [
            "sources/article-one.md",
            "sources/article-three.md",
        ]

    @pytest.mark.asyncio
    @patch("readpile.sync.llm.generate")
    async def test_skip_reply(self, mock_generate, tmp_path):
        mock_generate.return_value = json.dumps([
            {"type": "skip", "items": [2]},
        ])
        state = _state_with_digest(tmp_path)
        msg = _msg(
            sender="user@example.com",
            subject="Re: readpile — 2026-05-19 (3 new items)",
            text_body="Skip item 2",
        )
        provider = _mock_provider([msg])
        processor = ReplyProcessor(_config())
        actions = await processor.process(provider, state)

        assert len(actions) == 1
        assert isinstance(actions[0], SkipAction)
        assert actions[0].source_paths == ["sources/article-two.md"]


# ---------------------------------------------------------------------------
# Sender verification
# ---------------------------------------------------------------------------


class TestSenderVerification:
    """Only replies from the expected sender (config.sync.digest.to) are processed."""

    @pytest.mark.asyncio
    @patch("readpile.sync.llm.generate")
    async def test_wrong_sender_ignored(self, mock_generate, tmp_path):
        state = _state_with_digest(tmp_path)
        msg = _msg(
            sender="hacker@evil.com",
            subject="Re: readpile — 2026-05-19 (3 new items)",
            text_body="Synthesize all items",
        )
        provider = _mock_provider([msg])
        processor = ReplyProcessor(_config(to="user@example.com"))
        actions = await processor.process(provider, state)
        assert actions == []
        mock_generate.assert_not_called()

    @pytest.mark.asyncio
    @patch("readpile.sync.llm.generate")
    async def test_correct_sender_processed(self, mock_generate, tmp_path):
        mock_generate.return_value = json.dumps([
            {"type": "synthesize", "items": [1]},
        ])
        state = _state_with_digest(tmp_path)
        msg = _msg(
            sender="User@Example.COM",
            subject="Re: readpile — 2026-05-19 (3 new items)",
            text_body="synthesize 1",
        )
        provider = _mock_provider([msg])
        processor = ReplyProcessor(_config(to="user@example.com"))
        actions = await processor.process(provider, state)
        assert len(actions) == 1


# ---------------------------------------------------------------------------
# Conflicting replies → synthesize wins
# ---------------------------------------------------------------------------


class TestConflictResolution:
    """When the same item appears in both synthesize and skip, synthesize wins."""

    @pytest.mark.asyncio
    @patch("readpile.sync.llm.generate")
    async def test_synthesize_overrides_skip(self, mock_generate, tmp_path):
        mock_generate.return_value = json.dumps([
            {"type": "skip", "items": [1, 2]},
            {"type": "synthesize", "items": [1]},
        ])
        state = _state_with_digest(tmp_path)
        msg = _msg(
            sender="user@example.com",
            subject="Re: readpile — 2026-05-19 (3 new items)",
            text_body="Skip 1 and 2, actually synthesize 1",
        )
        provider = _mock_provider([msg])
        processor = ReplyProcessor(_config())
        actions = await processor.process(provider, state)

        synth_actions = [a for a in actions if isinstance(a, SynthesizeAction)]
        skip_actions = [a for a in actions if isinstance(a, SkipAction)]

        assert len(synth_actions) == 1
        assert "sources/article-one.md" in synth_actions[0].source_paths
        assert len(skip_actions) == 1
        assert "sources/article-one.md" not in skip_actions[0].source_paths
        assert "sources/article-two.md" in skip_actions[0].source_paths


# ---------------------------------------------------------------------------
# Rolling window matching (reply to older digest)
# ---------------------------------------------------------------------------


class TestRollingWindow:
    """Replies can match older digests in the history window."""

    @pytest.mark.asyncio
    @patch("readpile.sync.llm.generate")
    async def test_reply_to_older_digest(self, mock_generate, tmp_path):
        mock_generate.return_value = json.dumps([
            {"type": "synthesize", "items": [1]},
        ])
        state = SyncState(state_file=tmp_path / "state.json")
        # Add old digest
        state.set_digest_state(
            "readpile — 2026-05-15 (2 new items)",
            "digest_2026-05-15",
            {"1": "sources/old-article.md", "2": "sources/old-second.md"},
        )
        # Add newer digest
        state.set_digest_state(
            "readpile — 2026-05-19 (3 new items)",
            "digest_2026-05-19",
            {"1": "sources/new-article.md", "2": "sources/new-second.md", "3": "sources/new-third.md"},
        )

        msg = _msg(
            sender="user@example.com",
            subject="Re: readpile — 2026-05-15 (2 new items)",
            text_body="synthesize 1",
        )
        provider = _mock_provider([msg])
        processor = ReplyProcessor(_config())
        actions = await processor.process(provider, state)

        assert len(actions) == 1
        assert isinstance(actions[0], SynthesizeAction)
        assert actions[0].source_paths == ["sources/old-article.md"]


# ---------------------------------------------------------------------------
# Add/Remove source actions
# ---------------------------------------------------------------------------


class TestFeedActions:
    """Replies can add or remove feed subscriptions."""

    @pytest.mark.asyncio
    @patch("readpile.sync.llm.generate")
    async def test_add_feed_action(self, mock_generate, tmp_path):
        mock_generate.return_value = json.dumps([
            {"type": "add_feed", "url": "https://newblog.com/feed", "name": "New Blog"},
        ])
        state = _state_with_digest(tmp_path)
        msg = _msg(
            sender="user@example.com",
            subject="Re: readpile — 2026-05-19 (3 new items)",
            text_body="Add https://newblog.com to my feeds",
        )
        provider = _mock_provider([msg])
        processor = ReplyProcessor(_config())
        actions = await processor.process(provider, state)

        assert len(actions) == 1
        assert isinstance(actions[0], AddFeedAction)
        assert actions[0].url == "https://newblog.com/feed"
        assert actions[0].name == "New Blog"

    @pytest.mark.asyncio
    @patch("readpile.sync.llm.generate")
    async def test_remove_feed_action(self, mock_generate, tmp_path):
        mock_generate.return_value = json.dumps([
            {"type": "remove_feed", "name": "Old Blog"},
        ])
        state = _state_with_digest(tmp_path)
        msg = _msg(
            sender="user@example.com",
            subject="Re: readpile — 2026-05-19 (3 new items)",
            text_body="Remove Old Blog from feeds",
        )
        provider = _mock_provider([msg])
        processor = ReplyProcessor(_config())
        actions = await processor.process(provider, state)

        assert len(actions) == 1
        assert isinstance(actions[0], RemoveFeedAction)
        assert actions[0].name == "Old Blog"


# ---------------------------------------------------------------------------
# LLM failure
# ---------------------------------------------------------------------------


class TestLLMFailure:
    """When the LLM fails, replies should be silently skipped."""

    @pytest.mark.asyncio
    @patch("readpile.sync.llm.generate", side_effect=RuntimeError("API down"))
    async def test_llm_error_returns_empty(self, mock_generate, tmp_path):
        state = _state_with_digest(tmp_path)
        msg = _msg(
            sender="user@example.com",
            subject="Re: readpile — 2026-05-19 (3 new items)",
            text_body="synthesize everything",
        )
        provider = _mock_provider([msg])
        processor = ReplyProcessor(_config())
        actions = await processor.process(provider, state)
        assert actions == []


# ---------------------------------------------------------------------------
# Empty reply body
# ---------------------------------------------------------------------------


class TestEmptyReplyBody:
    """Empty reply text should not invoke the LLM."""

    @pytest.mark.asyncio
    @patch("readpile.sync.llm.generate")
    async def test_empty_body_no_llm_call(self, mock_generate, tmp_path):
        state = _state_with_digest(tmp_path)
        msg = _msg(
            sender="user@example.com",
            subject="Re: readpile — 2026-05-19 (3 new items)",
            text_body="",
        )
        provider = _mock_provider([msg])
        processor = ReplyProcessor(_config())
        actions = await processor.process(provider, state)
        assert actions == []
        mock_generate.assert_not_called()


# ---------------------------------------------------------------------------
# In-Reply-To header matching
# ---------------------------------------------------------------------------


class TestInReplyToMatching:
    """Replies with an In-Reply-To header matching a digest message_id are matched."""

    @pytest.mark.asyncio
    @patch("readpile.sync.llm.generate")
    async def test_in_reply_to_header(self, mock_generate, tmp_path):
        mock_generate.return_value = json.dumps([
            {"type": "synthesize", "items": [2]},
        ])
        state = _state_with_digest(tmp_path)
        msg = _msg(
            sender="user@example.com",
            subject="Fwd: something else entirely",
            text_body="synthesize 2",
            headers={"In-Reply-To": "digest_2026-05-19"},
        )
        provider = _mock_provider([msg])
        processor = ReplyProcessor(_config())
        actions = await processor.process(provider, state)

        assert len(actions) == 1
        assert isinstance(actions[0], SynthesizeAction)
        assert actions[0].source_paths == ["sources/article-two.md"]


# ---------------------------------------------------------------------------
# Provider fetch failure
# ---------------------------------------------------------------------------


class TestProviderFetchFailure:
    """If the email provider fails to fetch, return empty actions gracefully."""

    @pytest.mark.asyncio
    async def test_fetch_failure_returns_empty(self, tmp_path):
        state = _state_with_digest(tmp_path)
        provider = AsyncMock(spec=EmailProvider)
        provider.fetch_messages = AsyncMock(side_effect=ConnectionError("Network error"))
        processor = ReplyProcessor(_config())
        actions = await processor.process(provider, state)
        assert actions == []
