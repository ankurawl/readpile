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

    If Playwright is unavailable (not installed, browser missing, or launch
    failure), falls back to fetching HTML with httpx and running the article
    scraper only.
    """
    try:
        return await _scrape_with_playwright(url)
    except (ImportError, SystemExit, OSError, Exception) as exc:
        if isinstance(exc, ImportError) or isinstance(exc, SystemExit):
            pass
        elif "Executable doesn't exist" in str(exc) or "browser" in str(exc).lower():
            pass
        else:
            raise
    return await _scrape_with_httpx(url)


async def _scrape_with_playwright(url: str) -> ContentItem:
    """Scrape using Playwright (full browser rendering)."""
    from playwright.async_api import async_playwright

    from readpile.core.browser import launch_chromium
    from readpile.scrapers.article import scrape_article
    from readpile.scrapers.webpage import scrape_webpage

    async with async_playwright() as pw:
        browser = await launch_chromium(pw, headless=True)
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


async def _scrape_with_httpx(url: str) -> ContentItem:
    """Fallback: fetch HTML with httpx and extract article content."""
    import httpx

    from readpile.scrapers.article import scrape_article

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                resp = await client.get(url, headers={"User-Agent": "readpile/0.1"})
                resp.raise_for_status()
                html = resp.text
            return scrape_article(url, html)
        except (httpx.ConnectError, httpx.ReadError, httpx.PoolTimeout) as exc:
            last_exc = exc
            if attempt < 2:
                import asyncio
                await asyncio.sleep(1.0 * (attempt + 1))
                continue
            raise
        except Exception:
            raise
    raise last_exc  # unreachable, but satisfies type checker
