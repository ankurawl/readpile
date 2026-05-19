"""Gmail OAuth2 provider — reads the readpile inbox."""

from __future__ import annotations

import base64
import logging
import time
from datetime import datetime, timezone
from email import message_from_bytes
from email.utils import parsedate_to_datetime
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from readpile.sync.email.base import EmailMessage, EmailProvider

log = logging.getLogger("readpile.sync")


class TokenExpiredError(Exception):
    """Raised when OAuth token has expired and no browser is available."""


class GmailProvider(EmailProvider):
    """Gmail API provider using OAuth2 (gmail.readonly scope)."""

    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

    def __init__(self, credentials_file: Path, token_file: Path | None = None) -> None:
        self.credentials_file = Path(credentials_file).expanduser()
        self.token_file = (
            Path(token_file).expanduser() if token_file
            else self.credentials_file.parent / "email-token.json"
        )
        self._service = None

    async def connect(self) -> None:
        import asyncio
        await asyncio.to_thread(self._connect_sync)

    def _connect_sync(self) -> None:
        creds = None
        if self.token_file.exists():
            creds = Credentials.from_authorized_user_file(
                str(self.token_file), self.SCOPES,
            )

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as exc:
                log.warning("Token refresh failed: %s", exc)
                creds = None

        if not creds or not creds.valid:
            if not self.credentials_file.exists():
                raise FileNotFoundError(
                    f"Gmail credentials not found: {self.credentials_file}"
                )
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_file), self.SCOPES,
                )
                creds = flow.run_local_server(port=0)
            except Exception:
                raise TokenExpiredError(
                    "OAuth token expired. Run `readpile sync` interactively to re-authenticate."
                )

        self.token_file.write_text(creds.to_json())
        import os, stat
        try:
            os.chmod(self.token_file, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

        self._service = build("gmail", "v1", credentials=creds)

    async def fetch_messages(
        self,
        labels: list[str],
        since: datetime,
        max_results: int = 100,
    ) -> list[EmailMessage]:
        import asyncio
        return await asyncio.to_thread(
            self._fetch_sync, labels, since, max_results,
        )

    def _fetch_sync(
        self,
        labels: list[str],
        since: datetime,
        max_results: int,
    ) -> list[EmailMessage]:
        if self._service is None:
            raise RuntimeError("Not connected. Call connect() first.")

        since_epoch = int(since.timestamp())
        query = f"after:{since_epoch}"

        messages: list[EmailMessage] = []
        retries = 0
        max_retries = 3

        try:
            result = self._service.users().messages().list(
                userId="me",
                labelIds=labels,
                q=query,
                maxResults=max_results,
            ).execute()
        except HttpError as exc:
            if exc.resp.status == 429:
                while retries < max_retries:
                    retries += 1
                    delay = 2 ** retries
                    log.warning("Gmail rate limited, retrying in %ds", delay)
                    time.sleep(delay)
                    try:
                        result = self._service.users().messages().list(
                            userId="me",
                            labelIds=labels,
                            q=query,
                            maxResults=max_results,
                        ).execute()
                        break
                    except HttpError:
                        continue
                else:
                    raise
            else:
                raise

        msg_refs = result.get("messages", [])

        for ref in msg_refs:
            try:
                raw = self._service.users().messages().get(
                    userId="me",
                    id=ref["id"],
                    format="raw",
                ).execute()

                raw_bytes = base64.urlsafe_b64decode(raw["raw"])
                email_msg = message_from_bytes(raw_bytes)

                html_body = None
                text_body = None

                if email_msg.is_multipart():
                    for part in email_msg.walk():
                        ct = part.get_content_type()
                        if ct == "text/html" and html_body is None:
                            payload = part.get_payload(decode=True)
                            if payload:
                                html_body = payload.decode("utf-8", errors="replace")
                        elif ct == "text/plain" and text_body is None:
                            payload = part.get_payload(decode=True)
                            if payload:
                                text_body = payload.decode("utf-8", errors="replace")
                else:
                    ct = email_msg.get_content_type()
                    payload = email_msg.get_payload(decode=True)
                    if payload:
                        decoded = payload.decode("utf-8", errors="replace")
                        if ct == "text/html":
                            html_body = decoded
                        else:
                            text_body = decoded

                headers = {}
                for key in ("In-Reply-To", "List-Unsubscribe", "Message-ID", "References"):
                    val = email_msg.get(key)
                    if val:
                        headers[key] = val

                date = datetime.now(timezone.utc)
                date_str = email_msg.get("Date")
                if date_str:
                    try:
                        date = parsedate_to_datetime(date_str)
                    except Exception:
                        pass

                messages.append(EmailMessage(
                    message_id=ref["id"],
                    subject=email_msg.get("Subject", ""),
                    sender=email_msg.get("From", ""),
                    date=date,
                    html_body=html_body,
                    text_body=text_body,
                    headers=headers,
                    raw_size=raw.get("sizeEstimate", 0),
                ))
            except Exception as exc:
                log.warning("Failed to fetch message %s: %s", ref["id"], exc)
                continue

        return messages

    async def disconnect(self) -> None:
        self._service = None
