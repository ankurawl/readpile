"""CLI — crawl command.

Discover URLs from websites, blogs, and RSS/Atom feeds.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Optional
from urllib.parse import urlparse

import typer

from mediakit.core.config import load_config

app = typer.Typer()


# ---------------------------------------------------------------------------
# Mode detection
# ---------------------------------------------------------------------------

_RSS_EXTENSIONS = (".xml", ".rss", ".atom")
_RSS_PATH_SEGMENTS = ("/feed", "/rss", "/atom")


def _detect_crawl_mode(url: str) -> str:
    """Heuristically determine the crawl mode from a URL.

    Returns one of ``"rss"``, ``"blog"``, or ``"site"``.
    """
    parsed = urlparse(url)
    path_lower = parsed.path.lower()

    # RSS indicators: extension or path segment
    for ext in _RSS_EXTENSIONS:
        if path_lower.endswith(ext):
            return "rss"
    for seg in _RSS_PATH_SEGMENTS:
        if seg in path_lower:
            return "rss"

    # Blog heuristics: path contains /blog or common blog patterns
    if "/blog" in path_lower:
        return "blog"

    # Default to site crawl
    return "site"


# ---------------------------------------------------------------------------
# Per-mode crawl runners
# ---------------------------------------------------------------------------


def _crawl_rss(url: str, recent: int | None) -> list[str]:
    """Fetch an RSS/Atom feed and return entry URLs."""
    from mediakit.crawlers.rss import crawl_rss

    entries = crawl_rss(url, recent)
    return entries


def _crawl_blog(url: str, max_depth: int, max_pages: int, login: bool) -> list[str]:
    """Launch Playwright and discover blog post URLs."""
    from mediakit.crawlers.blog import BlogCrawler

    async def _run() -> list[str]:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            launch_kwargs: dict = {"headless": not login}
            if login:
                launch_kwargs["channel"] = "chrome"
            browser = await pw.chromium.launch(**launch_kwargs)

            context_kwargs: dict = {}
            if login:
                import os
                profile_dir = os.path.expanduser("~/.mediakit/browser-profile")
                os.makedirs(profile_dir, exist_ok=True)
                context_kwargs["storage_state"] = (
                    os.path.join(profile_dir, "state.json")
                    if os.path.exists(os.path.join(profile_dir, "state.json"))
                    else None
                )

            context = await browser.new_context(**context_kwargs)
            try:
                crawler = BlogCrawler(context, url, max_depth=max_depth, max_pages=max_pages)
                urls = await crawler.crawl()
                return urls
            finally:
                await context.close()
                await browser.close()

    return asyncio.run(_run())


def _crawl_site(
    url: str,
    max_depth: int,
    max_pages: int,
    scope: str,
) -> list[str]:
    """Recursively crawl a site and return discovered URLs."""
    from mediakit.crawlers.site import SiteCrawler

    crawler = SiteCrawler(url, max_depth=max_depth, scope=scope, max_pages=max_pages)

    # SiteCrawler.crawl() may be sync or async — handle both
    result = crawler.crawl()
    if asyncio.iscoroutine(result):
        return asyncio.run(result)
    return result


# ---------------------------------------------------------------------------
# Main command
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def main(
    url: Optional[str] = typer.Argument(
        None,
        help="URL to crawl for content.",
    ),
    mode: Optional[str] = typer.Option(
        None,
        "--mode",
        help="Crawl mode: auto, blog, site, rss (default: auto).",
    ),
    depth: Optional[int] = typer.Option(
        None,
        "--depth",
        help="Max crawl depth (default: 10).",
    ),
    max_pages: Optional[int] = typer.Option(
        None,
        "--max-pages",
        help="Max pages to discover (default: 100).",
    ),
    recent: Optional[int] = typer.Option(
        None,
        "--recent",
        help="Only return N most recent items (RSS mode).",
    ),
    scope: Optional[str] = typer.Option(
        None,
        "--scope",
        help="Crawl scope: prefix, domain (default: prefix).",
    ),
    login: bool = typer.Option(
        False,
        "--login",
        help="Use persistent browser profile for auth.",
    ),
) -> None:
    """Crawl a URL to discover content links."""

    if url is None:
        typer.echo("Error: Missing argument 'URL'.", err=True)
        raise typer.Exit(code=1)

    # ------------------------------------------------------------------
    # Load config and apply defaults
    # ------------------------------------------------------------------
    cfg = load_config()
    cc = cfg.get("crawl", {})

    depth = depth if depth is not None else cc.get("max_depth", 10)
    max_pages = max_pages if max_pages is not None else cc.get("max_pages", 100)
    scope = scope or cc.get("scope", "prefix")

    # Resolve mode
    effective_mode = mode or "auto"
    if effective_mode == "auto":
        effective_mode = _detect_crawl_mode(url)

    # ------------------------------------------------------------------
    # Dispatch to the appropriate crawler
    # ------------------------------------------------------------------
    urls: list[str] = []

    try:
        if effective_mode == "rss":
            urls = _crawl_rss(url, recent)
        elif effective_mode == "blog":
            urls = _crawl_blog(url, depth, max_pages, login)
        elif effective_mode == "site":
            urls = _crawl_site(url, depth, max_pages, scope)
        else:
            typer.echo(f"Error: Unknown mode '{effective_mode}'.", err=True)
            raise typer.Exit(code=1)
    except Exception as exc:
        typer.echo(f"Error crawling {url}: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    # ------------------------------------------------------------------
    # Output discovered URLs, one per line
    # ------------------------------------------------------------------
    for discovered_url in urls:
        sys.stdout.write(discovered_url + "\n")


if __name__ == "__main__":
    app()
