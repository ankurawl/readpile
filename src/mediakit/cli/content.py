"""CLI — content command.

Convenience orchestrator that auto-detects URL/source type and routes to
the correct extraction brick (transcribe, scrape, crawl), then optionally
archives the result.
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


def _process_single(source: str) -> list[ContentItem]:
    """Detect source type, extract content, and return ContentItem(s)."""
    url_type = detect_url_type(source)

    if url_type == URLType.youtube:
        from mediakit.transcribers.youtube import transcribe_youtube

        return [transcribe_youtube(source)]

    if url_type == URLType.audio_file and "://" in source:
        from mediakit.transcribers.audio import transcribe_from_url

        return [transcribe_from_url(source)]

    if url_type == URLType.audio_file:
        from mediakit.transcribers.audio import transcribe_audio

        return [transcribe_audio(Path(source))]

    if url_type == URLType.video and "://" in source:
        from mediakit.transcribers.audio import transcribe_from_url

        return [transcribe_from_url(source)]

    if url_type == URLType.video:
        from mediakit.transcribers.audio import transcribe_audio

        return [transcribe_audio(Path(source))]

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

    if url_type in (URLType.blog, URLType.website):
        from mediakit.scrapers import scrape_url

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


@app.callback(invoke_without_command=True)
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
    dir: Optional[Path] = typer.Option(  # noqa: UP007
        None,
        "--dir",
        help="Archive output directory (default from config).",
    ),
    archive: Optional[bool] = typer.Option(  # noqa: UP007
        None,
        "--archive/--no-archive",
        help="Force archiving on or off (default: use config auto_archive).",
    ),
) -> None:
    """Auto-detect source type, extract content, and optionally archive."""

    config = load_config()
    general_cfg = config.get("general", {})

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

    should_archive = archive if archive is not None else general_cfg.get("auto_archive", False)

    if should_archive:
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

    if len(items) == 1:
        typer.echo(items[0].to_stdout())
    else:
        typer.echo(ContentItem.to_batch(items))


if __name__ == "__main__":
    app()
