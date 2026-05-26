"""Scrapers package — article and webpage content extraction."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from readpile.core.models import ContentItem

log = logging.getLogger("readpile.sync")

_MIN_ARTICLE_LENGTH = 200

# Global Playwright state for batch processing
_playwright_instance = None
_browser_instance = None


async def _get_browser():
    """Lazily initialize and return a shared Playwright browser instance."""
    global _playwright_instance, _browser_instance
    if _browser_instance is None:
        from playwright.async_api import async_playwright
        from readpile.core.browser import launch_chromium
        
        _playwright_instance = await async_playwright().start()
        _browser_instance = await launch_chromium(_playwright_instance, headless=True)
    return _browser_instance


async def cleanup_browser():
    """Close the shared Playwright browser and stop the playwright instance."""
    global _playwright_instance, _browser_instance
    if _browser_instance:
        try:
            await _browser_instance.close()
        except Exception:
            pass
        _browser_instance = None
    if _playwright_instance:
        try:
            await _playwright_instance.stop()
        except Exception:
            pass
        _playwright_instance = None


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
        elif "Event loop is closed" in str(exc):
            log.warning("Playwright event loop closed unexpectedly, falling back to httpx")
        else:
            raise
    return await _scrape_with_httpx(url)


async def _scrape_with_playwright(url: str) -> ContentItem:
    """Scrape using Playwright (full browser rendering)."""
    from readpile.scrapers.article import scrape_article
    from readpile.scrapers.webpage import scrape_webpage

    browser = await _get_browser()
    context = await browser.new_context()
    page = await context.new_page()

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
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
        await page.close()
        await context.close()


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
