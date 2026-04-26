"""CLI — archive command.

Save ContentItems to disk as Markdown files with YAML front matter.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer

from mediakit.core.archiver import Archiver
from mediakit.core.config import load_config
from mediakit.core.models import ContentItem

app = typer.Typer()


@app.callback(invoke_without_command=True)
def main(
    dir: Optional[Path] = typer.Option(
        None,
        "--dir",
        help="Output directory (default: ~/mediakit-output or from config).",
    ),
    batch: bool = typer.Option(
        False,
        "--batch",
        help="Process batch items from stdin.",
    ),
) -> None:
    """Archive content items to disk as Markdown files."""

    # ------------------------------------------------------------------
    # Load config and resolve output directory
    # ------------------------------------------------------------------
    config = load_config()
    general_cfg = config.get("general", {})

    output_dir: Path
    if dir is not None:
        output_dir = Path(dir).expanduser()
    else:
        output_dir = Path(
            general_cfg.get("output_dir", "~/mediakit-output")
        ).expanduser()

    archiver = Archiver(output_dir)

    # ------------------------------------------------------------------
    # Read from stdin
    # ------------------------------------------------------------------
    raw = sys.stdin.read()

    if not raw.strip():
        typer.echo("Error: no input received on stdin.", err=True)
        raise typer.Exit(code=1)

    # ------------------------------------------------------------------
    # Batch mode — multiple items separated by ---CONTENT_ITEM---
    # ------------------------------------------------------------------
    if batch:
        items = ContentItem.from_stdin_batch(raw)

        if not items:
            typer.echo("No items found in batch input.", err=True)
            raise typer.Exit(code=1)

        for item in items:
            saved_path = archiver.save(item)
            typer.echo(f"Saved: {saved_path}", err=True)

        return

    # ------------------------------------------------------------------
    # Single mode — one ContentItem from stdin
    # ------------------------------------------------------------------
    item = ContentItem.from_stdin(raw)
    saved_path = archiver.save(item)
    typer.echo(f"Saved: {saved_path}", err=True)


if __name__ == "__main__":
    app()
