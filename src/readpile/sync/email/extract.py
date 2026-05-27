"""Email content extraction — newsletter/URL detection, trusted feed matching."""

from __future__ import annotations

import logging
import re
from email.utils import parseaddr

from readpile.sync.email.base import EmailMessage
from readpile.sync.sources import Feed

log = logging.getLogger("readpile.sync")

_KNOWN_NEWSLETTER_PLATFORMS = frozenset({
    "substack.com", "beehiiv.com", "convertkit.com", "buttondown.email",
    "mailchimp.com", "sendinblue.com", "mailerlite.com", "ghost.org",
    "revue.email", "getrevue.co",
})

_URL_RE = re.compile(r'https?://[^\s<>"\')\]]+')


def _extract_sender_domain(sender: str) -> str:
    _, addr = parseaddr(sender)
    if "@" in addr:
        return addr.split("@", 1)[1].lower()
    return ""


def _is_trusted_sender(sender: str, feeds: list[Feed], trusted_senders: list[str]) -> bool:
    _, addr = parseaddr(sender)
    addr = addr.lower()
    domain = _extract_sender_domain(sender)

    if addr in (s.lower() for s in trusted_senders):
        return True

    for s in feeds:
        source_domain = s.url.split("//", 1)[-1].split("/", 1)[0].lower().removeprefix("www.")
        if domain == source_domain or domain.endswith("." + source_domain):
            return True

    if domain in _KNOWN_NEWSLETTER_PLATFORMS:
        return True
    for platform in _KNOWN_NEWSLETTER_PLATFORMS:
        if domain.endswith("." + platform):
            return True

    return False


def _extract_urls(text: str) -> list[str]:
    urls = _URL_RE.findall(text)
    seen: set[str] = set()
    result: list[str] = []
    for u in urls:
        u = u.rstrip(".,;:!?)")
        lower = u.lower()
        if "unsubscribe" in lower or "mailto:" in lower:
            continue
        if u not in seen:
            seen.add(u)
            result.append(u)
    return result


def extract_content(
    msg: EmailMessage,
    feeds: list[Feed],
    config: dict,
) -> tuple[str, list[dict]]:
    """Extract content items from an email message.

    Returns (status, items) where status is one of:
    - "processed": items extracted
    - "skipped:unknown_sender": sender not trusted
    - "skipped:too_large": exceeds size limit
    - "skipped:empty": no extractable content
    """
    sync_cfg = config.get("sync", {})
    email_cfg = sync_cfg.get("email", {})
    trusted_senders = email_cfg.get("trusted_senders", [])
    max_size = sync_cfg.get("max_email_size_bytes", 5 * 1024 * 1024)

    if msg.raw_size > max_size:
        log.warning("Email from %s too large (%d bytes), skipping", msg.sender, msg.raw_size)
        return "skipped:too_large", []

    if not _is_trusted_sender(msg.sender, feeds, trusted_senders):
        log.info("Unknown sender: %s, skipping", msg.sender)
        return "skipped:unknown_sender", []

    skip_synth = False

    html = msg.html_body or ""
    text = msg.text_body or ""
    has_unsubscribe = "List-Unsubscribe" in msg.headers

    text_length = len(text) if text else 0
    html_length = len(html) if html else 0

    urls_in_text = _extract_urls(text) if text else []

    items: list[dict] = []

    is_newsletter = (
        (html_length > 500 or text_length > 500) or has_unsubscribe
    )

    if not is_newsletter and urls_in_text and text_length < 500:
        for url in urls_in_text[:3]:
            items.append({
                "kind": "url",
                "url": url,
                "title": msg.subject,
                "sender": msg.sender,
                "skip_synthesis": skip_synth,
            })
        return "processed", items

    if is_newsletter and html:
        items.append({
            "kind": "newsletter",
            "html": html,
            "title": msg.subject,
            "sender": msg.sender,
            "url": msg.sender,
            "skip_synthesis": skip_synth,
        })
        return "processed", items

    if text and urls_in_text:
        for url in urls_in_text[:3]:
            items.append({
                "kind": "url",
                "url": url,
                "title": msg.subject,
                "sender": msg.sender,
                "skip_synthesis": skip_synth,
            })
        return "processed", items

    if is_newsletter and text:
        items.append({
            "kind": "newsletter_text",
            "text": text,
            "title": msg.subject,
            "sender": msg.sender,
            "url": msg.sender,
            "skip_synthesis": skip_synth,
        })
        return "processed", items

    log.info("No extractable content from %s", msg.sender)
    return "skipped:empty", []
