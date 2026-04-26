"""CLI — summarize command.

Summarize content using an LLM provider (Ollama, Claude, OpenAI, or custom).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer

from mediakit.core.config import load_config
from mediakit.core.models import ContentItem

app = typer.Typer()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_yaml_front_matter(text: str) -> bool:
    """Return True if *text* starts with a YAML front matter block."""
    return text.strip().startswith("---")


def _extract_metadata(item: ContentItem) -> dict:
    """Extract metadata fields from a ContentItem for the summarizer."""
    meta: dict = {}
    if item.title:
        meta["title"] = item.title
    if item.channel:
        meta["channel"] = item.channel
    if item.duration:
        meta["duration"] = item.duration
    return meta


# ---------------------------------------------------------------------------
# Main command
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def main(
    input: Optional[Path] = typer.Argument(
        None,
        help="File to summarize (reads stdin if omitted and not a TTY).",
        exists=False,
    ),
    length: str = typer.Option(
        "medium",
        "--length",
        help="Summary length: small, medium, long.",
    ),
    provider: Optional[str] = typer.Option(
        None,
        "--provider",
        help="LLM provider: ollama, claude, openai, custom.",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        help="Model name override.",
    ),
    batch: bool = typer.Option(
        False,
        "--batch",
        help="Read batch items from stdin (split on ---CONTENT_ITEM---).",
    ),
    confirm: bool = typer.Option(
        False,
        "--confirm",
        help="Require confirmation before paid API calls in batch mode.",
    ),
) -> None:
    """Summarize content using an LLM."""

    # ------------------------------------------------------------------
    # Build CLI overrides and load config
    # ------------------------------------------------------------------
    cli_overrides: dict = {}
    if provider is not None:
        cli_overrides.setdefault("summarize", {})["provider"] = provider
    if model is not None:
        # Apply model override to the active provider section
        effective_provider = provider or "ollama"
        cli_overrides.setdefault("summarize", {}).setdefault(
            effective_provider, {}
        )["model"] = model

    config = load_config(cli_overrides if cli_overrides else None)
    summarize_cfg = config.get("summarize", {})

    # Use config default for length if not explicitly set
    if length == "medium":
        length = summarize_cfg.get("default_length", "medium")

    # ------------------------------------------------------------------
    # Obtain provider
    # ------------------------------------------------------------------
    from mediakit.summarizer.providers import get_provider

    llm_provider = get_provider(config)
    active_provider_name = summarize_cfg.get("provider", "ollama")

    # ------------------------------------------------------------------
    # Batch mode
    # ------------------------------------------------------------------
    if batch:
        raw = sys.stdin.read()
        items = ContentItem.from_stdin_batch(raw)

        if not items:
            typer.echo("No items found in batch input.", err=True)
            raise typer.Exit(code=1)

        # Confirmation gate for paid providers
        if confirm and active_provider_name in ("claude", "openai"):
            typer.echo(
                f"About to summarize {len(items)} item(s) using "
                f"{active_provider_name}. This will incur API costs.",
                err=True,
            )
            if not typer.confirm("Proceed?"):
                raise typer.Abort()

        from mediakit.summarizer.engine import summarize

        results: list[ContentItem] = []
        for item in items:
            metadata = _extract_metadata(item)
            summary_text = summarize(
                item.text, llm_provider, length, metadata
            )
            # Preserve metadata, replace body with summary
            item.text = summary_text
            item.word_count = len(summary_text.split())
            results.append(item)

        sys.stdout.write(ContentItem.to_batch(results) + "\n")
        return

    # ------------------------------------------------------------------
    # Single mode — read from file or stdin
    # ------------------------------------------------------------------
    raw_text: str

    if input is not None:
        # Read from file argument
        filepath = Path(input)
        if not filepath.exists():
            typer.echo(f"Error: File not found: {filepath}", err=True)
            raise typer.Exit(code=1)
        raw_text = filepath.read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        # Read from piped stdin
        raw_text = sys.stdin.read()
    else:
        typer.echo(
            "Error: provide a file argument or pipe content via stdin.",
            err=True,
        )
        raise typer.Exit(code=1)

    if not raw_text.strip():
        typer.echo("Error: empty input.", err=True)
        raise typer.Exit(code=1)

    # ------------------------------------------------------------------
    # Parse and summarize
    # ------------------------------------------------------------------
    from mediakit.summarizer.engine import summarize

    metadata: dict = {}
    text_to_summarize: str

    if _has_yaml_front_matter(raw_text):
        item = ContentItem.from_stdin(raw_text)
        metadata = _extract_metadata(item)
        text_to_summarize = item.text
    else:
        text_to_summarize = raw_text

    result = summarize(text_to_summarize, llm_provider, length, metadata)
    sys.stdout.write(result + "\n")


if __name__ == "__main__":
    app()
