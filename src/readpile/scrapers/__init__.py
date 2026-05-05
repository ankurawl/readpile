"""Scrapers package — article and webpage content extraction."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from readpile.core.models import ContentItem

_MIN_ARTICLE_LENGTH = 200


async def scrape_url(url: str) -> ContentItem:
    """Scrape a URL using Playwright with article-first fallback.

    Tries the article scraper first; falls back to the generic webpage
    scraper when the article result is missing or too short (< 200 chars).
    """
    from playwright.async_api import async_playwright

    from readpile.scrapers.article import scrape_article
    from readpile.scrapers.webpage import scrape_webpage

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            html = await page.content()

            item: ContentItem | None = None
            try:
                item = scrape_article(url, html)
            except Exception:
                item = None

            if item is None or len(item.text.strip()) < _MIN_ARTICLE_LENGTH:
                item = await scrape_webpage(url, page)

            return item
        finally:
            await browser.close()
