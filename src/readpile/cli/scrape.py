"""CLI command — scrape web pages using Playwright."""

from __future__ import annotations

import asyncio
import sys
from typing import Optional
import typer

from readpile.core.config import load_config
from readpile.core.models import ContentItem
from readpile.core.robots import RobotsChecker
from readpile.scrapers.article import scrape_article
from readpile.scrapers.webpage import scrape_webpage

app = typer.Typer()

# Minimum body length (in characters) to consider an article scrape successful.
_MIN_ARTICLE_LENGTH = 200


# ---------------------------------------------------------------------------
# Async implementation
# ---------------------------------------------------------------------------


async def _scrape_single_url(
    url: str,
    page,  # playwright Page
) -> ContentItem:
    """Navigate to *url*, extract content, and return a :class:`ContentItem`.

    Tries the article scraper first; falls back to the generic webpage
    scraper when the article result is missing or too short.
    """
    await page.goto(url, wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)

    html = await page.content()

    # Try article scraper first.
    item: ContentItem | None = None
    try:
        item = scrape_article(url, html)
    except Exception:
        item = None

    if item is None or len(item.text.strip()) < _MIN_ARTICLE_LENGTH:
        item = await scrape_webpage(url, page)

    return item


async def _run(
    urls: list[str],
    *,
    headless: bool,
    respect_robots: bool,
    rate_limit: float,
) -> list[ContentItem]:
    """Launch a browser, scrape every URL, and return the extracted items."""
    from playwright.async_api import async_playwright

    items: list[ContentItem] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()

        for idx, url in enumerate(urls):
            # Optional robots.txt check.
            if respect_robots:
                checker = RobotsChecker(url)
                checker.load()
                if not checker.can_fetch(url):
                    typer.echo(
                        f"Blocked by robots.txt: {url}", err=True
                    )
                    continue

            try:
                item = await _scrape_single_url(url, page)
                items.append(item)
            except Exception as exc:
                typer.echo(f"Error scraping {url}: {exc}", err=True)

            # Rate-limit between requests (skip after last URL).
            if rate_limit > 0 and idx < len(urls) - 1:
                await asyncio.sleep(rate_limit)

        await browser.close()

    return items


# ---------------------------------------------------------------------------
# Typer entry point
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def main(
    url: Optional[str] = typer.Argument(  # noqa: UP007
        None,
        help="URL to scrape (optional when using --batch).",
    ),
    batch: bool = typer.Option(
        False,
        "--batch",
        help="Read URLs from stdin, one per line.",
    ),
    headless: bool = typer.Option(
        None,
        "--headless/--no-headless",
        help="Run browser in headless mode (default: headless).",
    ),
    respect_robots: bool = typer.Option(
        None,
        "--respect-robots/--no-robots",
        help="Check robots.txt before scraping (default: respect).",
    ),
    rate_limit: Optional[float] = typer.Option(  # noqa: UP007
        None,
        "--rate-limit",
        help="Seconds to wait between requests (default: 1.0).",
    ),
) -> None:
    """Scrape a web page (or batch of pages) and output structured content."""

    # ---- Config: defaults < file/env < CLI flags ----
    cfg = load_config()
    scrape_cfg = cfg.get("scrape", {})

    effective_headless: bool = (
        headless if headless is not None else scrape_cfg.get("headless", True)
    )
    effective_robots: bool = (
        respect_robots
        if respect_robots is not None
        else scrape_cfg.get("respect_robots", True)
    )
    effective_rate: float = (
        rate_limit if rate_limit is not None else scrape_cfg.get("rate_limit", 1.0)
    )

    # ---- Collect URLs ----
    urls: list[str] = []

    if batch:
        for line in sys.stdin:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            urls.append(line)
    elif url is not None:
        urls.append(url)
    else:
        typer.echo("Error: provide a URL argument or use --batch.", err=True)
        raise typer.Exit(code=1)

    if not urls:
        typer.echo("No URLs to scrape.", err=True)
        raise typer.Exit(code=1)

    # ---- Run async scrape ----
    items = asyncio.run(
        _run(
            urls,
            headless=effective_headless,
            respect_robots=effective_robots,
            rate_limit=effective_rate,
        )
    )

    if not items:
        typer.echo("No content extracted.", err=True)
        raise typer.Exit(code=1)

    # ---- Output ----
    if len(items) == 1:
        typer.echo(items[0].to_stdout())
    else:
        typer.echo(ContentItem.to_batch(items))


if __name__ == "__main__":
    app()
