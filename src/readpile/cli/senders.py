"""CLI commands — readpile senders (list, add, remove, scan)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer
import tomlkit
from email.utils import parseaddr

app = typer.Typer()


def _get_config_doc() -> tuple[Path, tomlkit.TOMLDocument]:
    from readpile.core.config import get_config_path
    config_path = get_config_path()
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        doc = tomlkit.document()
        doc.add("sync", tomlkit.table())
        doc["sync"].add("email", tomlkit.table())
        doc["sync"]["email"].add("trusted_senders", tomlkit.array())
        return config_path, doc
    
    text = config_path.read_text(encoding="utf-8")
    return config_path, tomlkit.parse(text)


@app.command("list")
def senders_list() -> None:
    """List all trusted email senders."""
    _, doc = _get_config_doc()
    senders = doc.get("sync", {}).get("email", {}).get("trusted_senders", [])
    
    if not senders:
        typer.echo("No trusted senders configured.")
        return

    typer.echo("Trusted senders:")
    for i, email in enumerate(sorted(senders), 1):
        typer.echo(f"  {i}. {email}")


@app.command("add")
def senders_add(
    email: str = typer.Argument(..., help="Email address to trust"),
) -> None:
    """Add an email address to trusted senders."""
    _, addr = parseaddr(email)
    if not addr or "@" not in addr:
        typer.echo(f"Error: Invalid email address: {email}", err=True)
        raise typer.Exit(code=1)

    path, doc = _get_config_doc()
    sync = doc.setdefault("sync", tomlkit.table())
    email_cfg = sync.setdefault("email", tomlkit.table())
    trusted = email_cfg.setdefault("trusted_senders", tomlkit.array())

    if addr.lower() in (s.lower() for s in trusted):
        typer.echo(f"Sender {addr} is already trusted.")
        return

    trusted.append(addr.lower())
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")
    typer.echo(f"Added {addr} to trusted senders.")


@app.command("remove")
def senders_remove(
    email: str = typer.Argument(..., help="Email address to remove"),
) -> None:
    """Remove an email address from trusted senders."""
    path, doc = _get_config_doc()
    trusted = doc.get("sync", {}).get("email", {}).get("trusted_senders", [])

    if not trusted or email.lower() not in (s.lower() for s in trusted):
        typer.echo(f"Sender {email} not found in trusted senders.")
        return

    # Find the actual case-matched index to remove
    for i, s in enumerate(trusted):
        if s.lower() == email.lower():
            del trusted[i]
            break

    path.write_text(tomlkit.dumps(doc), encoding="utf-8")
    typer.echo(f"Removed {email} from trusted senders.")


@app.command("scan")
def senders_scan(
    days: int = typer.Option(7, "--days", "-d", help="How many days back to scan"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max number of senders to display"),
) -> None:
    """Scan recent emails for untrusted senders and add them interactively."""
    from datetime import datetime, timedelta, timezone
    from readpile.core.config import load_config
    from readpile.sync.pipeline import SyncPipeline
    from readpile.sync.email.extract import _is_trusted_sender
    from readpile.sync.sources import FeedRegistry

    config = load_config()
    email_cfg = config.get("sync", {}).get("email", {})
    if not email_cfg.get("enabled"):
        typer.echo("Error: Email sync is not enabled in config.toml", err=True)
        raise typer.Exit(code=1)

    # We need feeds to check if a sender is already trusted via feed domain
    from readpile.core.config import get_config_path
    config_dir = get_config_path().parent
    registry = FeedRegistry(config_dir / "feeds.toml")
    feeds = registry.load()

    # Reuse pipeline's provider logic
    wiki_dir = Path(config.get("wiki", {}).get("default_dir", ".")).expanduser()
    pipeline = SyncPipeline(config, wiki_dir)
    
    typer.echo(f"Connecting to email provider and scanning last {days} days...")
    
    async def _scan():
        provider = await pipeline._get_email_provider(email_cfg)
        since = datetime.now(timezone.utc) - timedelta(days=days)
        # Fetch labels from config, defaulting to ["INBOX"]
        labels = email_cfg.get("labels", ["INBOX"])
        # Fetch a decent batch to find unique senders
        messages = await provider.fetch_messages(labels=labels, since=since, max_results=100)
        
        untrusted_counts: dict[str, int] = {}
        for msg in messages:
            _, addr = parseaddr(msg.sender)
            if not addr:
                continue
            addr = addr.lower()
            
            # Use the core trust logic (it now checks trusted_senders too)
            if not _is_trusted_sender(msg.sender, feeds, email_cfg.get("trusted_senders", [])):
                untrusted_counts[addr] = untrusted_counts.get(addr, 0) + 1
        
        return untrusted_counts

    try:
        counts = asyncio.run(_scan())
    except Exception as exc:
        typer.echo(f"Error scanning emails: {exc}", err=True)
        raise typer.Exit(code=1)

    if not counts:
        typer.echo("No new untrusted senders found in recent emails.")
        return

    # Sort by frequency descending
    sorted_senders = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:limit]
    
    typer.echo("\nUntrusted senders found in recent emails:")
    for i, (addr, count) in enumerate(sorted_senders, 1):
        typer.echo(f"  {i:2}. {addr} ({count} emails)")

    typer.echo("\nEnter the numbers of the senders you want to trust (e.g., 1,3,5), or 'q' to quit.")
    selection = typer.prompt("Selection")
    
    if selection.lower() == 'q':
        return

    indices = []
    for part in selection.split(','):
        try:
            idx = int(part.strip())
            if 1 <= idx <= len(sorted_senders):
                indices.append(idx - 1)
        except ValueError:
            continue

    if not indices:
        typer.echo("No valid selections made.")
        return

    path, doc = _get_config_doc()
    sync = doc.setdefault("sync", tomlkit.table())
    email_cfg_toml = sync.setdefault("email", tomlkit.table())
    trusted = email_cfg_toml.setdefault("trusted_senders", tomlkit.array())

    added_count = 0
    for idx in indices:
        addr, _ = sorted_senders[idx]
        if addr not in (s.lower() for s in trusted):
            trusted.append(addr)
            added_count += 1
    
    if added_count > 0:
        path.write_text(tomlkit.dumps(doc), encoding="utf-8")
        typer.echo(f"Successfully added {added_count} new trusted sender(s).")
    else:
        typer.echo("All selected senders were already trusted.")
