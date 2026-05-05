"""CLI command — content-bot: start and manage the Telegram bot."""

from __future__ import annotations

import os
import typer

from mediakit.core.config import load_config

app = typer.Typer()


@app.command()
def start() -> None:
    """Start the Telegram bot."""

    cfg = load_config()

    token = cfg.get("bot", {}).get("token") or os.environ.get("TELEGRAM_BOT_TOKEN")

    if not token:
        typer.echo(
            "Error: TELEGRAM_BOT_TOKEN is not set.\n"
            "Set it as an environment variable or run `mediakit init` "
            "to create a config file.",
            err=True,
        )
        raise typer.Exit(code=1)

    from mediakit.bot.main import main

    main()


@app.command()
def status() -> None:
    """Check if the bot is configured."""

    cfg = load_config()

    token = cfg.get("bot", {}).get("token") or os.environ.get("TELEGRAM_BOT_TOKEN")
    token_ok = bool(token)
    typer.echo(f"Telegram token configured: {'yes' if token_ok else 'no'}")


if __name__ == "__main__":
    app()
