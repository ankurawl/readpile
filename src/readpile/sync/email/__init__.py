"""Email provider package."""

from readpile.sync.email.base import EmailProvider, EmailMessage

__all__ = ["EmailProvider", "EmailMessage"]

try:
    from readpile.sync.email.gmail import GmailProvider
    __all__.append("GmailProvider")
except ImportError:
    pass
