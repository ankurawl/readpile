"""CLI commands — readpile wiki: manage LLM-maintained wikis."""

from __future__ import annotations

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
        typer.echo("Error: No wiki directory specified. Use --wiki or set [wiki] default_dir.")
        raise typer.Exit(1)
    return Path(default).expanduser().resolve()


@app.command()
def init(
    path: str = typer.Argument(..., help="Directory path for the new wiki."),
    name: str = typer.Option(..., "--name", help="Wiki name."),
    description: str = typer.Option("", "--description", help="Wiki description."),
    categories: Optional[str] = typer.Option(None, "--categories", help="Comma-separated categories."),
) -> None:
    """Create a new wiki with directory structure and conventions."""
    from readpile.wiki import WikiStore

    cat_list = [c.strip() for c in categories.split(",")] if categories else None
    store = WikiStore(path)
    try:
        wiki_path = store.init(name, description, cat_list)
        typer.echo(f"Wiki created at {wiki_path}")
    except FileExistsError as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(1)


@app.command("list")
def list_pages(
    wiki: Optional[str] = typer.Option(None, "--wiki", help="Wiki directory."),
    category: Optional[str] = typer.Option(None, "--category", help="Filter by category."),
) -> None:
    """List all wiki pages with metadata."""
    from readpile.wiki import WikiStore

    path = _resolve_wiki(wiki)
    store = WikiStore(path)
    if not store.exists():
        typer.echo(f"Error: No wiki found at {path}. Run 'readpile wiki init' first.")
        raise typer.Exit(1)

    pages = store.list_pages(category)
    if not pages:
        typer.echo("No pages found.")
        return
    for p in pages:
        typer.echo(f"{p['name']} — {p['title']} [{p['category']}]")


@app.command()
def search(
    query: str = typer.Argument(..., help="Search term."),
    wiki: Optional[str] = typer.Option(None, "--wiki", help="Wiki directory."),
    scope: str = typer.Option("pages", "--scope", help="Search scope: pages, sources, all."),
) -> None:
    """Full-text search across wiki pages and/or sources."""
    from readpile.wiki import WikiStore

    path = _resolve_wiki(wiki)
    store = WikiStore(path)
    if not store.exists():
        typer.echo(f"Error: No wiki found at {path}.")
        raise typer.Exit(1)

    results = store.search(query, scope)
    if not results:
        typer.echo("No results found.")
        return
    for r in results:
        typer.echo(f"\n{r['name']} — {r['title']}")
        for m in r["matches"]:
            typer.echo(f"  Line {m['line_number']}:")
            for line in m["context"].splitlines():
                typer.echo(f"    {line}")


@app.command()
def log(
    wiki: Optional[str] = typer.Option(None, "--wiki", help="Wiki directory."),
    recent: Optional[int] = typer.Option(None, "--recent", help="Show only N recent entries."),
) -> None:
    """View wiki operation log."""
    from readpile.wiki import WikiStore

    path = _resolve_wiki(wiki)
    store = WikiStore(path)
    if not store.exists():
        typer.echo(f"Error: No wiki found at {path}.")
        raise typer.Exit(1)

    text = store.read_log(recent)
    typer.echo(text)
