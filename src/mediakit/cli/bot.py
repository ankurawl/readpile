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

    # Resolve token: config (via env overlay) or direct env lookup.
    token = cfg.get("bot", {}).get("token") or os.environ.get("TELEGRAM_BOT_TOKEN")

    if not token:
        typer.echo(
            "Error: TELEGRAM_BOT_TOKEN is not set.\n"
            "Set it as an environment variable or run `mediakit init` "
            "to create a config file.",
            err=True,
        )
        raise typer.Exit(code=1)

    from mediakit.bot.main import main  # noqa: WPS433 — lazy import

    main()


@app.command()
def status() -> None:
    """Check if the bot is configured."""

    cfg = load_config()

    # --- Token ---
    token = cfg.get("bot", {}).get("token") or os.environ.get("TELEGRAM_BOT_TOKEN")
    token_ok = bool(token)
    typer.echo(f"Telegram token configured: {'yes' if token_ok else 'no'}")

    # --- LLM provider / model ---
    summarize_cfg = cfg.get("summarize", {})
    provider = summarize_cfg.get("provider", "ollama")
    provider_cfg = summarize_cfg.get(provider, {})
    model = provider_cfg.get("model", "unknown")
    typer.echo(f"LLM provider: {provider}")
    typer.echo(f"Model: {model}")

    # --- Ollama reachability ---
    ollama_host = (
        cfg.get("summarize", {}).get("ollama", {}).get("host", "http://localhost:11434")
    )
    ollama_reachable = False
    try:
        import urllib.request

        req = urllib.request.Request(ollama_host, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            ollama_reachable = resp.status == 200
    except Exception:
        ollama_reachable = False

    typer.echo(f"Ollama reachable ({ollama_host}): {'yes' if ollama_reachable else 'no'}")


if __name__ == "__main__":
    app()
