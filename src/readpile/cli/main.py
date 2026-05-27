"""CLI entry point — parent app that registers all subcommands."""

from __future__ import annotations

import typer

from readpile.cli.init import app as init_app
from readpile.cli.wiki import app as wiki_app
from readpile.cli.sync import sync_app, synthesize_app, feeds_app, status_app
from readpile.cli.senders import app as senders_app
from readpile.cli.clean import app as clean_app

app = typer.Typer()

app.registered_commands += init_app.registered_commands
app.add_typer(wiki_app, name="wiki", help="Wiki management commands.")
app.registered_commands += sync_app.registered_commands
app.registered_commands += synthesize_app.registered_commands
app.add_typer(feeds_app, name="feeds", help="Manage feed subscriptions.")
app.add_typer(senders_app, name="senders", help="Manage trusted email senders.")
app.add_typer(clean_app, name="clean", help="Mass administrative deletions.")
app.registered_commands += status_app.registered_commands


if __name__ == "__main__":
    app()
