"""Tests for readpile.bot.handlers — message and command handlers."""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("telegram")

from readpile.bot.handlers import (
    admin_add_handler,
    admin_list_handler,
    admin_remove_handler,
    help_handler,
    history_handler,
    set_language_handler,
    set_style_handler,
    start_handler,
    url_message_handler,
    whoami_handler,
)
from readpile.bot.preferences import get_preferences, set_preference
from readpile.bot.whitelist import add_to_whitelist, is_whitelisted, load_whitelist
from readpile.core.detector import URLType


ADMIN_CHAT_ID = 12345
USER_CHAT_ID = 67890


@pytest.fixture
def data_dir(tmp_path):
    return str(tmp_path)


@pytest.fixture
def config(data_dir):
    return {
        "admin_chat_id": ADMIN_CHAT_ID,
        "data_dir": data_dir,
    }


@pytest.fixture
def mock_update():
    update = AsyncMock()
    update.effective_chat.id = ADMIN_CHAT_ID
    update.effective_user.username = "testuser"
    update.message.reply_text = AsyncMock()
    update.message.reply_document = AsyncMock()
    update.message.text = ""
    return update


@pytest.fixture
def mock_context(config):
    context = AsyncMock()
    context.bot_data = {"config": config}
    context.args = []
    return context


class TestStartHandler:
    @pytest.mark.asyncio
    async def test_sends_welcome_message(self, mock_update, mock_context):
        await start_handler(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once()
        msg = mock_update.message.reply_text.call_args[0][0]
        assert "readpile" in msg
        assert "/help" in msg


class TestHelpHandler:
    @pytest.mark.asyncio
    async def test_sends_help_message(self, mock_update, mock_context):
        await help_handler(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once()
        msg = mock_update.message.reply_text.call_args[0][0]
        assert "/start" in msg
        assert "/help" in msg
        assert "/whoami" in msg


class TestWhoamiHandler:
    @pytest.mark.asyncio
    async def test_returns_chat_id(self, mock_update, mock_context):
        await whoami_handler(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once()
        msg = mock_update.message.reply_text.call_args[0][0]
        assert str(ADMIN_CHAT_ID) in msg


class TestSetLanguageHandler:
    @pytest.mark.asyncio
    async def test_sets_language(self, mock_update, mock_context, data_dir):
        mock_context.args = ["es"]
        await set_language_handler(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once()
        msg = mock_update.message.reply_text.call_args[0][0]
        assert "es" in msg

    @pytest.mark.asyncio
    async def test_no_args_shows_usage(self, mock_update, mock_context):
        mock_context.args = []
        await set_language_handler(mock_update, mock_context)
        msg = mock_update.message.reply_text.call_args[0][0]
        assert "Usage" in msg

    @pytest.mark.asyncio
    async def test_non_whitelisted_user_ignored(self, mock_update, mock_context):
        mock_update.effective_chat.id = 99999
        mock_context.args = ["fr"]
        await set_language_handler(mock_update, mock_context)
        mock_update.message.reply_text.assert_not_called()


class TestSetStyleHandler:
    @pytest.mark.asyncio
    async def test_sets_brief_style(self, mock_update, mock_context):
        mock_context.args = ["brief"]
        await set_style_handler(mock_update, mock_context)
        msg = mock_update.message.reply_text.call_args[0][0]
        assert "brief" in msg

    @pytest.mark.asyncio
    async def test_rejects_invalid_style(self, mock_update, mock_context):
        mock_context.args = ["invalid_style"]
        await set_style_handler(mock_update, mock_context)
        msg = mock_update.message.reply_text.call_args[0][0]
        assert "Invalid style" in msg

    @pytest.mark.asyncio
    async def test_no_args_shows_usage(self, mock_update, mock_context):
        mock_context.args = []
        await set_style_handler(mock_update, mock_context)
        msg = mock_update.message.reply_text.call_args[0][0]
        assert "Usage" in msg


class TestHistoryHandler:
    @pytest.mark.asyncio
    async def test_empty_history(self, mock_update, mock_context):
        await history_handler(mock_update, mock_context)
        msg = mock_update.message.reply_text.call_args[0][0]
        assert "No items" in msg

    @pytest.mark.asyncio
    async def test_shows_history(self, mock_update, mock_context, data_dir):
        from readpile.bot.preferences import add_to_history

        add_to_history(ADMIN_CHAT_ID, {
            "title": "Test Video",
            "url": "https://youtube.com/watch?v=abc",
        }, data_dir)

        await history_handler(mock_update, mock_context)
        msg = mock_update.message.reply_text.call_args[0][0]
        assert "Test Video" in msg
        assert "Recent items" in msg


class TestAdminAddHandler:
    @pytest.mark.asyncio
    async def test_admin_can_add_user(self, mock_update, mock_context, data_dir):
        mock_context.args = [str(USER_CHAT_ID)]
        await admin_add_handler(mock_update, mock_context)
        msg = mock_update.message.reply_text.call_args[0][0]
        assert "Added" in msg
        assert USER_CHAT_ID in load_whitelist(data_dir)

    @pytest.mark.asyncio
    async def test_non_admin_rejected(self, mock_update, mock_context):
        mock_update.effective_chat.id = USER_CHAT_ID
        mock_context.args = ["99999"]
        await admin_add_handler(mock_update, mock_context)
        msg = mock_update.message.reply_text.call_args[0][0]
        assert "not authorized" in msg

    @pytest.mark.asyncio
    async def test_duplicate_add(self, mock_update, mock_context, data_dir):
        add_to_whitelist(USER_CHAT_ID, data_dir)
        mock_context.args = [str(USER_CHAT_ID)]
        await admin_add_handler(mock_update, mock_context)
        msg = mock_update.message.reply_text.call_args[0][0]
        assert "already" in msg

    @pytest.mark.asyncio
    async def test_no_args_shows_usage(self, mock_update, mock_context):
        mock_context.args = []
        await admin_add_handler(mock_update, mock_context)
        msg = mock_update.message.reply_text.call_args[0][0]
        assert "Usage" in msg

    @pytest.mark.asyncio
    async def test_invalid_chat_id(self, mock_update, mock_context):
        mock_context.args = ["not_a_number"]
        await admin_add_handler(mock_update, mock_context)
        msg = mock_update.message.reply_text.call_args[0][0]
        assert "Invalid" in msg


class TestAdminRemoveHandler:
    @pytest.mark.asyncio
    async def test_admin_can_remove_user(self, mock_update, mock_context, data_dir):
        add_to_whitelist(USER_CHAT_ID, data_dir)
        mock_context.args = [str(USER_CHAT_ID)]
        await admin_remove_handler(mock_update, mock_context)
        msg = mock_update.message.reply_text.call_args[0][0]
        assert "Removed" in msg

    @pytest.mark.asyncio
    async def test_remove_non_existent(self, mock_update, mock_context):
        mock_context.args = ["99999"]
        await admin_remove_handler(mock_update, mock_context)
        msg = mock_update.message.reply_text.call_args[0][0]
        assert "was not" in msg

    @pytest.mark.asyncio
    async def test_non_admin_rejected(self, mock_update, mock_context):
        mock_update.effective_chat.id = USER_CHAT_ID
        mock_context.args = [str(ADMIN_CHAT_ID)]
        await admin_remove_handler(mock_update, mock_context)
        msg = mock_update.message.reply_text.call_args[0][0]
        assert "not authorized" in msg


class TestAdminListHandler:
    @pytest.mark.asyncio
    async def test_empty_whitelist(self, mock_update, mock_context):
        await admin_list_handler(mock_update, mock_context)
        msg = mock_update.message.reply_text.call_args[0][0]
        assert "empty" in msg.lower() or "Whitelist is empty" in msg

    @pytest.mark.asyncio
    async def test_shows_whitelisted_ids(self, mock_update, mock_context, data_dir):
        add_to_whitelist(USER_CHAT_ID, data_dir)
        await admin_list_handler(mock_update, mock_context)
        msg = mock_update.message.reply_text.call_args[0][0]
        assert str(USER_CHAT_ID) in msg

    @pytest.mark.asyncio
    async def test_non_admin_rejected(self, mock_update, mock_context):
        mock_update.effective_chat.id = USER_CHAT_ID
        await admin_list_handler(mock_update, mock_context)
        msg = mock_update.message.reply_text.call_args[0][0]
        assert "not authorized" in msg


class TestUrlMessageHandler:
    @pytest.mark.asyncio
    async def test_ignores_messages_without_urls(self, mock_update, mock_context):
        mock_update.message.text = "hello, no urls here"
        await url_message_handler(mock_update, mock_context)
        mock_update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_non_whitelisted_user(self, mock_update, mock_context):
        mock_update.effective_chat.id = 99999
        mock_update.message.text = "https://www.youtube.com/watch?v=abc123"
        await url_message_handler(mock_update, mock_context)
        mock_update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    @patch("readpile.bot.handlers.add_to_history")
    @patch("readpile.bot.handlers.create_content_document")
    @patch("readpile.bot.handlers.format_content_message")
    @patch("readpile.bot.handlers.transcribe_youtube")
    @patch("readpile.bot.handlers.detect_url_type")
    async def test_youtube_url_happy_path(
        self,
        mock_detect,
        mock_transcribe,
        mock_format_msg,
        mock_create_doc,
        mock_add_history,
        mock_update,
        mock_context,
    ):
        from readpile.core.models import ContentItem, ContentType

        mock_update.message.text = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

        mock_detect.return_value = URLType.youtube
        mock_transcribe.return_value = ContentItem(
            text="This is the transcript text.",
            title="Test Video",
            source_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            content_type=ContentType.youtube,
            channel="Test Channel",
            duration="5:00",
        )
        mock_format_msg.return_value = "<b>Test Video</b>\nContent..."
        mock_create_doc.return_value = (b"document bytes", "2026-04-25_test-video.md")

        status_msg = AsyncMock()
        mock_update.message.reply_text.return_value = status_msg

        await url_message_handler(mock_update, mock_context)

        mock_detect.assert_called_once()
        mock_transcribe.assert_called_once()
        mock_format_msg.assert_called_once()
        mock_create_doc.assert_called_once()
        mock_update.message.reply_document.assert_called_once()

    @pytest.mark.asyncio
    @patch("readpile.bot.handlers.format_error_message")
    @patch("readpile.bot.handlers.detect_url_type")
    async def test_video_not_found_error(
        self,
        mock_detect,
        mock_format_error,
        mock_update,
        mock_context,
    ):
        from readpile.transcribers.youtube import VideoNotFoundError

        mock_update.message.text = "https://www.youtube.com/watch?v=invalid"
        mock_detect.return_value = URLType.youtube
        mock_format_error.return_value = "<b>Error</b>\n\nVideo not found. Check the URL"

        status_msg = AsyncMock()
        mock_update.message.reply_text.return_value = status_msg

        with patch("readpile.bot.handlers.transcribe_youtube", side_effect=VideoNotFoundError("Video not found. Check the URL")):
            await url_message_handler(mock_update, mock_context)

        status_msg.edit_text.assert_called()
        mock_format_error.assert_called_once_with("Video not found. Check the URL")

    @pytest.mark.asyncio
    @patch("readpile.bot.handlers.format_error_message")
    @patch("readpile.bot.handlers.detect_url_type")
    async def test_unexpected_error_handled_gracefully(
        self,
        mock_detect,
        mock_format_error,
        mock_update,
        mock_context,
    ):
        mock_update.message.text = "https://www.youtube.com/watch?v=abc123"
        mock_detect.side_effect = RuntimeError("Something unexpected")
        mock_format_error.return_value = "<b>Error</b>\n\nAn unexpected error occurred."

        status_msg = AsyncMock()
        mock_update.message.reply_text.return_value = status_msg

        await url_message_handler(mock_update, mock_context)

        status_msg.edit_text.assert_called()
        mock_format_error.assert_called_once_with(
            "An unexpected error occurred. Please try again."
        )
