"""CLI entry point — parent app that registers all subcommands."""

from __future__ import annotations

import typer

from readpile.cli.init import app as init_app
from readpile.cli.wiki import app as wiki_app

app = typer.Typer()

app.registered_commands += init_app.registered_commands
app.add_typer(wiki_app, name="wiki", help="Wiki management commands.")


if __name__ == "__main__":
    app()
