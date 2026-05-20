"""CLI — content command.

Convenience orchestrator that auto-detects URL/source type and routes to
the correct extractor (transcribe, scrape, crawl), and prints to stdout.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Optional

import typer

from readpile.core.detector import URLType, detect_url_type
from readpile.core.models import ContentItem, ContentType

app = typer.Typer()


def _process_single(source: str) -> list[ContentItem]:
    """Detect source type, extract content, and return ContentItem(s)."""
    url_type = detect_url_type(source)

    if url_type == URLType.youtube:
        from readpile.transcribers.youtube import transcribe_youtube

        return [transcribe_youtube(source)]

    if url_type == URLType.audio_file and "://" in source:
        from readpile.transcribers.audio import transcribe_from_url

        return [transcribe_from_url(source)]

    if url_type == URLType.audio_file:
        from readpile.transcribers.audio import transcribe_audio

        return [transcribe_audio(Path(source))]

    if url_type == URLType.video and "://" in source:
        from readpile.transcribers.audio import transcribe_from_url

        return [transcribe_from_url(source)]

    if url_type == URLType.video:
        from readpile.transcribers.audio import transcribe_audio

        return [transcribe_audio(Path(source))]

    if url_type == URLType.rss:
        from readpile.crawlers.rss import crawl_rss

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

    if url_type in (URLType.blog, URLType.website):
        from readpile.scrapers import scrape_url

        return [asyncio.run(scrape_url(source))]

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

    typer.echo(f"Unsupported source type for: {source}", err=True)
    raise typer.Exit(code=1)


@app.command()
def main(
    source: Optional[str] = typer.Argument(  # noqa: UP007
        None,
        help="URL or local file to process.",
    ),
    batch: bool = typer.Option(
        False,
        "--batch",
        help="Process multiple URLs from stdin (one per line).",
    ),
) -> None:
    """Auto-detect source type, extract content, and print to stdout."""

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

    if len(items) == 1:
        typer.echo(items[0].to_stdout())
    else:
        typer.echo(ContentItem.to_batch(items))


if __name__ == "__main__":
    app()
