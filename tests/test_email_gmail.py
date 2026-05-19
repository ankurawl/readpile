"""Tests for readpile.sync.email.gmail — GmailProvider."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestGmailProvider:
    def test_token_expiry_raises(self, tmp_path):
        from readpile.sync.email.gmail import GmailProvider, TokenExpiredError

        creds_file = tmp_path / "credentials.json"
        creds_file.write_text('{"installed": {"client_id": "x"}}')
        token_file = tmp_path / "token.json"

        provider = GmailProvider(creds_file, token_file)

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "tok"
        mock_creds.refresh.side_effect = Exception("Token expired")

        with patch("readpile.sync.email.gmail.Credentials") as mock_cls:
            mock_cls.from_authorized_user_file.return_value = mock_creds

            with patch("readpile.sync.email.gmail.InstalledAppFlow") as mock_flow:
                mock_flow.from_client_secrets_file.return_value.run_local_server.side_effect = Exception("No browser")

                with pytest.raises(TokenExpiredError):
                    provider._connect_sync()

    def test_connect_creates_service(self, tmp_path):
        from readpile.sync.email.gmail import GmailProvider

        creds_file = tmp_path / "credentials.json"
        creds_file.write_text('{"installed": {"client_id": "x"}}')
        token_file = tmp_path / "token.json"
        token_file.write_text('{"token": "test"}')

        provider = GmailProvider(creds_file, token_file)

        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds.expired = False
        mock_creds.to_json.return_value = '{"token": "test"}'

        with patch("readpile.sync.email.gmail.Credentials") as mock_cls, \
             patch("readpile.sync.email.gmail.build") as mock_build:
            mock_cls.from_authorized_user_file.return_value = mock_creds
            mock_build.return_value = MagicMock()
            provider._connect_sync()
            assert provider._service is not None

    def test_fetch_returns_messages(self, tmp_path):
        from readpile.sync.email.gmail import GmailProvider

        creds_file = tmp_path / "credentials.json"
        creds_file.write_text('{}')

        provider = GmailProvider(creds_file)
        mock_service = MagicMock()
        provider._service = mock_service

        import base64
        raw_email = (
            b"From: test@example.com\r\n"
            b"Subject: Test\r\n"
            b"Date: Mon, 19 May 2025 08:00:00 +0000\r\n"
            b"Message-ID: <msg1@example.com>\r\n"
            b"\r\n"
            b"Hello world"
        )
        encoded = base64.urlsafe_b64encode(raw_email).decode()

        mock_list = MagicMock()
        mock_list.execute.return_value = {"messages": [{"id": "msg1"}]}
        mock_service.users.return_value.messages.return_value.list.return_value = mock_list

        mock_get = MagicMock()
        mock_get.execute.return_value = {
            "id": "msg1",
            "raw": encoded,
            "sizeEstimate": len(raw_email),
        }
        mock_service.users.return_value.messages.return_value.get.return_value = mock_get

        since = datetime(2025, 5, 18, tzinfo=timezone.utc)
        messages = provider._fetch_sync(["INBOX"], since, 10)

        assert len(messages) == 1
        assert messages[0].message_id == "msg1"
        assert messages[0].subject == "Test"
        assert "test@example.com" in messages[0].sender
        assert messages[0].text_body == "Hello world"

    def test_disconnect_clears_service(self):
        import asyncio
        from readpile.sync.email.gmail import GmailProvider

        provider = GmailProvider(Path("/fake"))
        provider._service = MagicMock()
        asyncio.run(provider.disconnect())
        assert provider._service is None

    def test_missing_credentials_raises(self, tmp_path):
        from readpile.sync.email.gmail import GmailProvider

        creds_file = tmp_path / "nonexistent.json"
        provider = GmailProvider(creds_file)

        with patch("readpile.sync.email.gmail.Credentials") as mock_cls:
            mock_cls.from_authorized_user_file.side_effect = FileNotFoundError

            with pytest.raises(FileNotFoundError):
                provider._connect_sync()
