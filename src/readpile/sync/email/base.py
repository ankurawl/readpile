"""Email provider ABC + EmailMessage dataclass."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class EmailMessage:
    """A single email message with parsed content."""

    message_id: str
    subject: str
    sender: str
    date: datetime
    html_body: str | None = None
    text_body: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    raw_size: int = 0


class EmailProvider(ABC):
    """Abstract email provider with async context manager."""

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def fetch_messages(
        self,
        labels: list[str],
        since: datetime,
        max_results: int = 100,
    ) -> list[EmailMessage]: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *exc):
        await self.disconnect()
