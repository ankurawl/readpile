"""CLI — content command.

Convenience orchestrator that auto-detects URL/source type and routes to
the correct brick chain (transcribe, scrape, crawl), then optionally
summarizes and archives the result.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Optional

import typer

from mediakit.core.archiver import Archiver
from mediakit.core.config import load_config
from mediakit.core.detector import URLType, detect_url_type
from mediakit.core.models import ContentItem, ContentType

app = typer.Typer()


# ---------------------------------------------------------------------------
# Minimum article length before falling back to the webpage scraper.
# ---------------------------------------------------------------------------

_MIN_ARTICLE_LENGTH = 200


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_metadata(item: ContentItem) -> dict:
    """Pull summarizer-relevant metadata from a ContentItem."""
    meta: dict = {}
    if item.title:
        meta["title"] = item.title
    if item.channel:
        meta["channel"] = item.channel
    if item.duration:
        meta["duration"] = item.duration
    return meta


async def _scrape_url(url: str) -> ContentItem:
    """Scrape a blog/website URL using Playwright.

    Tries the article scraper first; falls back to the generic webpage
    scraper when the article result is missing or too short.
    """
    from playwright.async_api import async_playwright

    from mediakit.scrapers.article import scrape_article
    from mediakit.scrapers.webpage import scrape_webpage

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            html = await page.content()

            # Try the structured article scraper first.
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


def _process_single(source: str) -> list[ContentItem]:
    """Detect source type, extract content, and return ContentItem(s)."""
    url_type = detect_url_type(source)

    # ---- YouTube --------------------------------------------------------
    if url_type == URLType.youtube:
        from mediakit.transcribers.youtube import transcribe_youtube

        return [transcribe_youtube(source)]

    # ---- Audio file (remote URL) ----------------------------------------
    if url_type == URLType.audio_file and "://" in source:
        from mediakit.transcribers.audio import transcribe_from_url

        return [transcribe_from_url(source)]

    # ---- Audio file (local) ---------------------------------------------
    if url_type == URLType.audio_file:
        from mediakit.transcribers.audio import transcribe_audio

        return [transcribe_audio(Path(source))]

    # ---- Video URL (Vimeo, Loom, direct video link) ---------------------
    if url_type == URLType.video and "://" in source:
        from mediakit.transcribers.audio import transcribe_from_url

        return [transcribe_from_url(source)]

    # ---- Video local file -----------------------------------------------
    if url_type == URLType.video:
        from mediakit.transcribers.audio import transcribe_audio

        return [transcribe_audio(Path(source))]

    # ---- RSS feed -------------------------------------------------------
    if url_type == URLType.rss:
        from mediakit.crawlers.rss import crawl_rss

        entry_urls = crawl_rss(source)
        if not entry_urls:
            typer.echo(f"No entries found in feed: {source}", err=True)
            return []

        items: list[ContentItem] = []
        for entry_url in entry_urls:
            try:
                sub_items = _process_single(entry_url)
                items.extend(sub_items)
            except Exception as exc:
                typer.echo(
                    f"Error processing feed entry {entry_url}: {exc}",
                    err=True,
                )
        return items

    # ---- Blog / Website -------------------------------------------------
    if url_type in (URLType.blog, URLType.website):
        return [asyncio.run(_scrape_url(source))]

    # ---- Local file (text) ----------------------------------------------
    if url_type == URLType.local_file:
        filepath = Path(source)
        if not filepath.exists():
            typer.echo(f"Error: file not found: {source}", err=True)
            raise typer.Exit(code=1)

        text = filepath.read_text(encoding="utf-8")
        return [
            ContentItem(
                text=text,
                title=filepath.stem,
                source_url=str(filepath.resolve()),
                content_type=ContentType.article,
            )
        ]

    # Should not be reached, but handle gracefully.
    typer.echo(f"Unsupported source type for: {source}", err=True)
    raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Main command
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def main(
    source: Optional[str] = typer.Argument(  # noqa: UP007
        None,
        help="URL or local file to process.",
    ),
    no_summary: bool = typer.Option(
        False,
        "--no-summary",
        help="Skip summarization.",
    ),
    summary_length: str = typer.Option(
        "medium",
        "--summary-length",
        help="Summary length: small, medium, long.",
    ),
    batch: bool = typer.Option(
        False,
        "--batch",
        help="Process multiple URLs from stdin (one per line).",
    ),
    dir: Optional[Path] = typer.Option(  # noqa: UP007
        None,
        "--dir",
        help="Archive output directory (default from config).",
    ),
    provider: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--provider",
        help="LLM provider for summarization.",
    ),
    model: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--model",
        help="Model name for summarization.",
    ),
    no_archive: bool = typer.Option(
        False,
        "--no-archive",
        help="Skip archiving (just print to stdout).",
    ),
) -> None:
    """Auto-detect source type and process: extract, summarize, archive."""

    # ------------------------------------------------------------------
    # Load config
    # ------------------------------------------------------------------
    cli_overrides: dict = {}
    if provider is not None:
        cli_overrides.setdefault("summarize", {})["provider"] = provider
    if model is not None:
        effective_provider = provider or "ollama"
        cli_overrides.setdefault("summarize", {}).setdefault(
            effective_provider, {}
        )["model"] = model

    config = load_config(cli_overrides if cli_overrides else None)
    general_cfg = config.get("general", {})
    summarize_cfg = config.get("summarize", {})

    # Resolve summary length from config default when not overridden.
    if summary_length == "medium":
        summary_length = summarize_cfg.get("default_length", "medium")

    # ------------------------------------------------------------------
    # Collect sources
    # ------------------------------------------------------------------
    sources: list[str] = []

    if batch:
        for line in sys.stdin:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            sources.append(line)
    elif source is not None:
        sources.append(source)
    else:
        typer.echo(
            "Error: provide a SOURCE argument or use --batch.", err=True
        )
        raise typer.Exit(code=1)

    if not sources:
        typer.echo("No sources to process.", err=True)
        raise typer.Exit(code=1)

    # ------------------------------------------------------------------
    # Extract content
    # ------------------------------------------------------------------
    items: list[ContentItem] = []

    for src in sources:
        try:
            extracted = _process_single(src)
            items.extend(extracted)
        except typer.Exit:
            raise
        except Exception as exc:
            typer.echo(f"Error processing {src}: {exc}", err=True)

    if not items:
        typer.echo("No content extracted.", err=True)
        raise typer.Exit(code=1)

    # ------------------------------------------------------------------
    # Summarize
    # ------------------------------------------------------------------
    if not no_summary:
        from mediakit.summarizer.engine import summarize
        from mediakit.summarizer.providers import get_provider

        llm_provider = get_provider(config)

        for item in items:
            metadata = _extract_metadata(item)
            try:
                summary_text = summarize(
                    item.text, llm_provider, summary_length, metadata
                )
                item.text = summary_text
                item.word_count = len(summary_text.split())
            except Exception as exc:
                typer.echo(
                    f"Summarization failed for '{item.title}': {exc}",
                    err=True,
                )

    # ------------------------------------------------------------------
    # Archive
    # ------------------------------------------------------------------
    if not no_archive:
        output_dir: Path
        if dir is not None:
            output_dir = Path(dir).expanduser()
        else:
            output_dir = Path(
                general_cfg.get("output_dir", "~/mediakit-output")
            ).expanduser()

        archiver = Archiver(output_dir)
        for item in items:
            saved_path = archiver.save(item)
            typer.echo(f"Saved: {saved_path}", err=True)

    # ------------------------------------------------------------------
    # Output to stdout
    # ------------------------------------------------------------------
    if len(items) == 1:
        typer.echo(items[0].to_stdout())
    else:
        typer.echo(ContentItem.to_batch(items))


if __name__ == "__main__":
    app()
