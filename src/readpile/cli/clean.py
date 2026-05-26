"""CLI commands — readpile clean: mass administrative deletions."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer()


def _resolve_wiki(wiki: str | None) -> Path:
    if wiki:
        return Path(wiki).expanduser().resolve()
    from readpile.core.config import load_config
    config = load_config()
    default = config.get("wiki", {}).get("default_dir", "")
    if not default:
        return Path("~/my-wiki").expanduser().resolve()
    return Path(default).expanduser().resolve()


@app.command("feeds")
def clean_feeds(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation."),
) -> None:
    """Clear all feed subscriptions from feeds.toml."""
    from readpile.core.config import get_config_path
    
    config_dir = get_config_path().parent
    feeds_toml = config_dir / "feeds.toml"
    
    if not feeds_toml.exists():
        typer.echo("No feeds.toml found.")
        return
        
    if not force:
        typer.confirm("Are you sure you want to delete all feed subscriptions?", abort=True)
        
    feeds_toml.write_text("", encoding="utf-8")
    typer.echo("Cleared feeds.toml")


@app.command("pages")
def clean_pages(
    wiki: Optional[str] = typer.Option(None, "--wiki", help="Wiki directory."),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation."),
) -> None:
    """Delete all wiki pages and rebuild index."""
    from readpile.wiki import WikiStore

    path = _resolve_wiki(wiki)
    store = WikiStore(path)
    if not store.exists():
        typer.echo(f"Error: No wiki found at {path}.", err=True)
        raise typer.Exit(1)

    if not force:
        typer.confirm(f"Are you sure you want to delete all pages in wiki '{path}'?", abort=True)

    count = 0
    for p in store.pages_dir.glob("*.md"):
        p.unlink()
        count += 1
    
    index_content = store.build_index()
    store.index_path.write_text(index_content, encoding="utf-8")
    typer.echo(f"Deleted {count} pages and rebuilt index.")


@app.command("sources")
def clean_sources(
    wiki: Optional[str] = typer.Option(None, "--wiki", help="Wiki directory."),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation."),
) -> None:
    """Delete all saved sources in the wiki."""
    from readpile.wiki import WikiStore

    path = _resolve_wiki(wiki)
    store = WikiStore(path)
    if not store.exists():
        typer.echo(f"Error: No wiki found at {path}.", err=True)
        raise typer.Exit(1)

    if not force:
        typer.confirm(f"Are you sure you want to delete all sources in wiki '{path}'?", abort=True)

    count = 0
    for p in store.sources_dir.glob("*.md"):
        p.unlink()
        count += 1
    typer.echo(f"Deleted {count} sources.")


@app.command("configs")
def clean_configs(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation."),
) -> None:
    """Delete the entire ~/.readpile directory (configs and state)."""
    from readpile.core.config import get_config_path
    
    config_dir = get_config_path().parent
    
    if not config_dir.exists():
        typer.echo(f"Directory {config_dir} does not exist.")
        return
        
    if not force:
        typer.confirm(f"Are you sure you want to delete the entire configuration directory {config_dir}?", abort=True)
        
    shutil.rmtree(config_dir)
    typer.echo(f"Deleted {config_dir}")


@app.command("all")
def clean_all(
    wiki: Optional[str] = typer.Option(None, "--wiki", help="Wiki directory."),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation."),
) -> None:
    """Execute all clean commands (feeds, pages, sources, configs)."""
    if not force:
        typer.confirm("Are you sure you want to perform a TOTAL CLEANUP (feeds, pages, sources, configs)?", abort=True)
    
    # We do pages and sources first before deleting the config that might point to the wiki
    try:
        clean_pages(wiki=wiki, force=True)
    except Exception as e:
        typer.echo(f"Warning cleaning pages: {e}")
        
    try:
        clean_sources(wiki=wiki, force=True)
    except Exception as e:
        typer.echo(f"Warning cleaning sources: {e}")
        
    try:
        clean_feeds(force=True)
    except Exception as e:
        typer.echo(f"Warning cleaning feeds: {e}")
        
    try:
        clean_configs(force=True)
    except Exception as e:
        typer.echo(f"Warning cleaning configs: {e}")
        
    typer.echo("Total cleanup complete.")
