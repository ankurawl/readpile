"""CLI — transcribe command.

Transcribe audio/video from URLs or local files using YouTube captions
or Whisper-based engines.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Optional

import typer

from readpile.core.config import load_config
from readpile.core.detector import URLType, detect_url_type
from readpile.core.models import ContentItem

app = typer.Typer()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _transcribe_single(
    source: str,
    language: str,
    engine: str,
    model: str,
    diarize: bool,
) -> ContentItem:
    """Route a single source to the appropriate transcriber and return a
    :class:`ContentItem`.

    Raises :class:`typer.Exit` on unrecoverable errors.
    """
    url_type = detect_url_type(source)

    try:
        if url_type == URLType.youtube:
            from readpile.transcribers.youtube import transcribe_youtube

            return transcribe_youtube(source, language)

        if url_type == URLType.audio_file and ("://" in source):
            # Remote audio URL
            from readpile.transcribers.audio import transcribe_from_url

            return transcribe_from_url(source, model, diarize)

        if url_type in (URLType.audio_file, URLType.local_file, URLType.video):
            # Local file on disk
            from readpile.transcribers.audio import transcribe_audio

            return transcribe_audio(Path(source), model, diarize)

        # For any other URL type (blog, website, video hosting), try the
        # audio URL path — the transcriber can download and convert.
        from readpile.transcribers.audio import transcribe_from_url

        return transcribe_from_url(source, model, diarize)

    except Exception as exc:
        typer.echo(f"Error transcribing {source}: {exc}", err=True)
        raise typer.Exit(code=1) from exc


# ---------------------------------------------------------------------------
# Main command
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def main(
    source: Optional[str] = typer.Argument(
        None,
        help="URL or local file to transcribe.",
    ),
    batch: bool = typer.Option(
        False,
        "--batch",
        help="Read sources from stdin (one per line).",
    ),
    language: Optional[str] = typer.Option(
        None,
        "--language",
        help="Transcript language code (default: en).",
    ),
    engine: Optional[str] = typer.Option(
        None,
        "--engine",
        help="Transcription engine: auto, whisper, whisperx (default: auto).",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        help="Whisper model size: tiny, base, small, medium, large (default: base).",
    ),
    diarize: Optional[bool] = typer.Option(
        None,
        "--diarize/--no-diarize",
        help="Speaker diarization (default: no-diarize).",
    ),
) -> None:
    """Transcribe audio/video from a URL or local file."""

    # ------------------------------------------------------------------
    # Load config and apply defaults
    # ------------------------------------------------------------------
    cfg = load_config()
    tc = cfg.get("transcribe", {})

    language = language or tc.get("language", "en")
    engine = engine or tc.get("engine", "auto")
    model = model or tc.get("whisper_model", "base")
    if diarize is None:
        diarize = tc.get("diarize", False)

    # ------------------------------------------------------------------
    # Batch mode — read sources from stdin
    # ------------------------------------------------------------------
    if batch:
        items: list[ContentItem] = []
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            item = _transcribe_single(line, language, engine, model, diarize)
            items.append(item)

        if items:
            sys.stdout.write(ContentItem.to_batch(items) + "\n")
        return

    # ------------------------------------------------------------------
    # Single source mode
    # ------------------------------------------------------------------
    if source is None:
        typer.echo("Error: Missing argument 'SOURCE'.", err=True)
        raise typer.Exit(code=1)

    item = _transcribe_single(source, language, engine, model, diarize)
    sys.stdout.write(item.to_stdout())


if __name__ == "__main__":
    app()
