"""Tests for readpile.sync.email.extract — newsletter detection, trusted sender matching, URL extraction."""

from __future__ import annotations

from datetime import datetime, timezone

from readpile.sync.email.base import EmailMessage
from readpile.sync.email.extract import extract_content, _extract_sender_domain, _is_trusted_sender
from readpile.sync.sources import Source


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _msg(
    *,
    sender: str = "alice@example.com",
    subject: str = "Test",
    html_body: str | None = None,
    text_body: str | None = None,
    headers: dict[str, str] | None = None,
    raw_size: int = 0,
) -> EmailMessage:
    return EmailMessage(
        message_id="<msg-001>",
        subject=subject,
        sender=sender,
        date=datetime.now(timezone.utc),
        html_body=html_body,
        text_body=text_body,
        headers=headers or {},
        raw_size=raw_size,
    )


def _source(url: str, name: str = "Test") -> Source:
    return Source(name=name, url=url, kind="rss")


def _config(
    *,
    skip_synthesis_senders: list[str] | None = None,
    max_email_size_bytes: int | None = None,
) -> dict:
    email_cfg: dict = {}
    if skip_synthesis_senders is not None:
        email_cfg["skip_synthesis_senders"] = skip_synthesis_senders
    sync_cfg: dict = {"email": email_cfg}
    if max_email_size_bytes is not None:
        sync_cfg["max_email_size_bytes"] = max_email_size_bytes
    return {"sync": sync_cfg}


# ---------------------------------------------------------------------------
# Newsletter detection
# ---------------------------------------------------------------------------


class TestNewsletterDetection:
    """Emails with long HTML bodies and/or List-Unsubscribe are newsletters."""

    def test_html_over_500_chars_is_newsletter(self):
        html = "<html><body>" + "x" * 600 + "</body></html>"
        msg = _msg(sender="news@example.com", html_body=html)
        sources = [_source("https://example.com")]
        status, items = extract_content(msg, sources, _config())
        assert status == "processed"
        assert len(items) == 1
        assert items[0]["kind"] == "newsletter"

    def test_list_unsubscribe_header_is_newsletter(self):
        html = "<html><body>Short content</body></html>"
        msg = _msg(
            sender="news@example.com",
            html_body=html,
            headers={"List-Unsubscribe": "<mailto:unsubscribe@example.com>"},
        )
        sources = [_source("https://example.com")]
        status, items = extract_content(msg, sources, _config())
        assert status == "processed"
        assert len(items) == 1
        assert items[0]["kind"] == "newsletter"

    def test_text_over_500_chars_newsletter(self):
        text = "x" * 600
        msg = _msg(sender="news@example.com", text_body=text)
        sources = [_source("https://example.com")]
        status, items = extract_content(msg, sources, _config())
        assert status == "processed"
        assert len(items) == 1
        assert items[0]["kind"] == "newsletter_text"
        assert items[0]["text"] == text

    def test_newsletter_html_preferred_over_text(self):
        html = "<html><body>" + "x" * 600 + "</body></html>"
        msg = _msg(
            sender="news@example.com",
            html_body=html,
            text_body="Also has text " * 50,
        )
        sources = [_source("https://example.com")]
        status, items = extract_content(msg, sources, _config())
        assert status == "processed"
        assert items[0]["kind"] == "newsletter"
        assert items[0]["html"] == html


# ---------------------------------------------------------------------------
# Trusted source matching
# ---------------------------------------------------------------------------


class TestTrustedSourceMatching:
    """Only emails from trusted senders are processed."""

    def test_configured_source_domain_is_trusted(self):
        msg = _msg(sender="alerts@myblog.com", text_body="x" * 600)
        sources = [_source("https://myblog.com/feed")]
        status, items = extract_content(msg, sources, _config())
        assert status == "processed"

    def test_subdomain_of_configured_source_is_trusted(self):
        msg = _msg(sender="noreply@mail.myblog.com", text_body="x" * 600)
        sources = [_source("https://myblog.com/feed")]
        status, items = extract_content(msg, sources, _config())
        assert status == "processed"

    def test_unknown_sender_is_skipped(self):
        msg = _msg(sender="stranger@unknown.org", text_body="x" * 600)
        sources = [_source("https://myblog.com/feed")]
        status, items = extract_content(msg, sources, _config())
        assert status == "skipped:unknown_sender"
        assert items == []

    def test_known_platform_substack_is_trusted(self):
        msg = _msg(sender="writer@substack.com", html_body="x" * 600)
        sources = []
        status, items = extract_content(msg, sources, _config())
        assert status == "processed"

    def test_known_platform_subdomain_is_trusted(self):
        msg = _msg(sender="writer@newsletter.beehiiv.com", html_body="x" * 600)
        sources = []
        status, items = extract_content(msg, sources, _config())
        assert status == "processed"

    def test_www_prefix_stripped_from_source_url(self):
        msg = _msg(sender="hello@example.com", text_body="x" * 600)
        sources = [_source("https://www.example.com")]
        status, items = extract_content(msg, sources, _config())
        assert status == "processed"


# ---------------------------------------------------------------------------
# Email size limit
# ---------------------------------------------------------------------------


class TestEmailSizeLimit:
    """Emails exceeding the configured size limit are skipped."""

    def test_over_default_limit_skipped(self):
        msg = _msg(
            sender="news@example.com",
            html_body="x" * 600,
            raw_size=6 * 1024 * 1024,
        )
        sources = [_source("https://example.com")]
        status, items = extract_content(msg, sources, _config())
        assert status == "skipped:too_large"
        assert items == []

    def test_custom_limit(self):
        msg = _msg(
            sender="news@example.com",
            html_body="x" * 600,
            raw_size=2000,
        )
        sources = [_source("https://example.com")]
        status, _ = extract_content(msg, sources, _config(max_email_size_bytes=1000))
        assert status == "skipped:too_large"

    def test_under_limit_processed(self):
        msg = _msg(
            sender="news@example.com",
            html_body="x" * 600,
            raw_size=1000,
        )
        sources = [_source("https://example.com")]
        status, items = extract_content(msg, sources, _config())
        assert status == "processed"
        assert len(items) == 1

    def test_size_check_before_sender_check(self):
        """Size limit is checked before sender trust, so an oversized email
        from an unknown sender gets 'skipped:too_large', not 'skipped:unknown_sender'."""
        msg = _msg(
            sender="unknown@nowhere.org",
            html_body="x" * 600,
            raw_size=10 * 1024 * 1024,
        )
        status, _ = extract_content(msg, [], _config())
        assert status == "skipped:too_large"


# ---------------------------------------------------------------------------
# Forwarded URL detection
# ---------------------------------------------------------------------------


class TestForwardedUrlDetection:
    """Short emails with URLs are treated as forwarded links, not newsletters."""

    def test_short_body_with_urls(self):
        text = "Check this out: https://example.com/article"
        msg = _msg(sender="friend@substack.com", text_body=text)
        sources = []
        status, items = extract_content(msg, sources, _config())
        assert status == "processed"
        assert len(items) == 1
        assert items[0]["kind"] == "url"
        assert items[0]["url"] == "https://example.com/article"

    def test_multiple_urls_limited_to_three(self):
        urls = [f"https://example.com/article-{i}" for i in range(10)]
        text = "Check these: " + " ".join(urls)
        msg = _msg(sender="friend@substack.com", text_body=text)
        sources = []
        status, items = extract_content(msg, sources, _config())
        assert status == "processed"
        assert len(items) == 3

    def test_unsubscribe_urls_are_filtered(self):
        text = "Read: https://example.com/article https://example.com/unsubscribe"
        msg = _msg(sender="friend@substack.com", text_body=text)
        sources = []
        status, items = extract_content(msg, sources, _config())
        assert status == "processed"
        assert all("unsubscribe" not in item["url"] for item in items)


# ---------------------------------------------------------------------------
# No extractable content
# ---------------------------------------------------------------------------


class TestEmptyContent:
    """Emails with no usable content are skipped."""

    def test_empty_body(self):
        msg = _msg(sender="news@example.com")
        sources = [_source("https://example.com")]
        status, items = extract_content(msg, sources, _config())
        assert status == "skipped:empty"
        assert items == []

    def test_short_text_no_urls(self):
        msg = _msg(sender="news@example.com", text_body="Thanks!")
        sources = [_source("https://example.com")]
        status, items = extract_content(msg, sources, _config())
        assert status == "skipped:empty"
        assert items == []


# ---------------------------------------------------------------------------
# skip_synthesis_senders
# ---------------------------------------------------------------------------


class TestSkipSynthesisSenders:
    """Senders in skip_synthesis_senders are trusted but items get skip_synthesis=True."""

    def test_skip_synthesis_sender_is_trusted(self):
        msg = _msg(sender="noreply@promotions.example.com", html_body="x" * 600)
        sources = []
        config = _config(skip_synthesis_senders=["noreply@promotions.example.com"])
        status, items = extract_content(msg, sources, config)
        assert status == "processed"
        assert items[0]["skip_synthesis"] is True

    def test_non_skip_synthesis_sender(self):
        msg = _msg(sender="writer@substack.com", html_body="x" * 600)
        sources = []
        config = _config(skip_synthesis_senders=["other@example.com"])
        status, items = extract_content(msg, sources, config)
        assert status == "processed"
        assert items[0]["skip_synthesis"] is False

    def test_skip_synthesis_case_insensitive(self):
        msg = _msg(sender="NoReply@Example.COM", html_body="x" * 600)
        sources = []
        config = _config(skip_synthesis_senders=["noreply@example.com"])
        status, items = extract_content(msg, sources, config)
        assert status == "processed"
        assert items[0]["skip_synthesis"] is True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class TestExtractSenderDomain:
    def test_simple_address(self):
        assert _extract_sender_domain("alice@example.com") == "example.com"

    def test_display_name(self):
        assert _extract_sender_domain("Alice <alice@example.com>") == "example.com"

    def test_no_at(self):
        assert _extract_sender_domain("nope") == ""
