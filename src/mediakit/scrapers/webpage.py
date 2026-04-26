"""Webpage scraper — general-purpose HTML content extraction.

Migrated from site-downloader's extract_content() logic. Uses a cascade of
CSS selectors to find the most meaningful content container on a page,
falling back to <body> if nothing better is found.

Requires a Playwright Page object to be passed in (the caller owns the
browser lifecycle).
"""

from __future__ import annotations

import asyncio
import re

from mediakit.core.models import ContentItem, ContentType


# ---------------------------------------------------------------------------
# Dependency guard
# ---------------------------------------------------------------------------


def _check_deps() -> None:
    """Verify Playwright is installed (checked when actually scraping)."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        raise SystemExit(
            "Webpage scraping requires Playwright. Install with:\n"
            "  pip install mediakit\n"
            "  or: pip install playwright && playwright install chromium\n"
        )


# ---------------------------------------------------------------------------
# JavaScript executed inside the browser to extract main text content.
# Tries progressively less-specific selectors; returns the first element
# whose trimmed innerText exceeds 50 characters.
# ---------------------------------------------------------------------------
_CONTENT_EXTRACTION_JS = """
() => {
    const selectors = [
        '[data-site-canvas="true"]',
        'main',
        '[role="main"]',
        'article',
        '.content',
        '#content',
        '.wiki-content',
        '.page-content',
        '.document-content',
        'body'
    ];
    for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el && el.innerText.trim().length > 50) {
            return el.innerText;
        }
    }
    return document.body.innerText;
}
"""

# Separators commonly used to append a site name to the page title.
_TITLE_SEPARATORS = re.compile(r" [-|—–] ")

# Maximum length of a suffix segment to be considered a "site name" and
# stripped. Longer suffixes are likely part of the real title.
_MAX_SUFFIX_LENGTH = 40


def _clean_title(raw_title: str) -> str:
    """Remove site-name suffixes from a page title.

    Handles common patterns like:
        "My Article - Site Name"
        "My Article | Site Name"
        "My Article — Site Name"
        "My Article – Site Name"

    If the last segment after splitting is short (<=40 chars) it is treated as
    a site name and dropped. Otherwise the full title is returned as-is.
    """
    raw_title = raw_title.strip()
    if not raw_title:
        return raw_title

    parts = _TITLE_SEPARATORS.split(raw_title)
    if len(parts) <= 1:
        return raw_title

    # Only strip the suffix if it looks like a short site name.
    suffix = parts[-1].strip()
    if len(suffix) <= _MAX_SUFFIX_LENGTH:
        # Rejoin everything except the last part.
        # We need to reconstruct without the last separator + suffix.
        # Find the last occurrence of any separator in the original string.
        # Use rfind for each candidate and pick the rightmost match.
        sep_candidates = [" - ", " | ", " — ", " – "]
        last_pos = -1
        for sep in sep_candidates:
            pos = raw_title.rfind(sep)
            if pos > last_pos:
                last_pos = pos
        if last_pos > 0:
            return raw_title[:last_pos].strip()

    return raw_title


async def scrape_webpage(url: str, page: "Page | None" = None) -> ContentItem:
    """Extract text content from a webpage using Playwright.

    Parameters
    ----------
    url:
        The URL to scrape.
    page:
        A Playwright ``Page`` object. The caller is responsible for creating
        and closing the browser/context. If *None* is passed, a
        ``ValueError`` is raised — standalone browser management is not
        provided by this function.

    Returns
    -------
    ContentItem
        A content item with ``content_type=ContentType.webpage``.
    """
    _check_deps()

    if page is None:
        raise ValueError(
            "A Playwright Page object must be provided. "
            "Create one via `browser.new_page()` before calling scrape_webpage()."
        )

    # Navigate and wait for initial DOM, then allow extra time for JS-rendered
    # content (SPAs, lazy-loaded sections, etc.).
    await page.goto(url, wait_until="domcontentloaded")
    await asyncio.sleep(2)

    # Extract the main text via the selector cascade.
    text_content: str = await page.evaluate(_CONTENT_EXTRACTION_JS)
    text_content = text_content.strip()

    # Retrieve and clean the page title.
    raw_title = await page.title()
    clean_title = _clean_title(raw_title)

    return ContentItem(
        content_type=ContentType.webpage,
        text=text_content,
        title=clean_title,
        source_url=url,
    )
