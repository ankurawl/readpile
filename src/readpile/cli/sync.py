"""CLI commands — readpile sync, synthesize, feeds, status."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

sync_app = typer.Typer()
synthesize_app = typer.Typer()
feeds_app = typer.Typer()
status_app = typer.Typer()


@sync_app.command("sync")
def sync(
    wiki: Optional[str] = typer.Option(None, help="Wiki directory path"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Fetch but don't save or send"),
    no_email: bool = typer.Option(False, "--no-email", help="Skip email stage"),
    no_feeds: bool = typer.Option(False, "--no-feeds", help="Skip feed crawling"),
    no_digest: bool = typer.Option(False, "--no-digest", help="Skip digest email"),
    reset_feeds: bool = typer.Option(False, "--reset-feeds", help="Clear feed state only"),
    reset_all: bool = typer.Option(False, "--reset-all", help="Clear all sync state"),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Verbose output"),
) -> None:
    """Check email and feeds for new content, send daily digest."""
    import asyncio
    from readpile.core.config import load_config
    from readpile.sync.pipeline import SyncPipeline

    config = load_config()
    wiki_dir = Path(wiki or config.get("wiki", {}).get("default_dir", "")).expanduser()
    if not wiki_dir or not (wiki_dir / ".wiki.toml").exists():
        typer.echo("Error: No wiki found. Run `readpile wiki init` first.", err=True)
        raise typer.Exit(code=1)

    pipeline = SyncPipeline(config, wiki_dir, dry_run=dry_run)
    result = asyncio.run(pipeline.run(
        no_email=no_email,
        no_feeds=no_feeds,
        no_digest=no_digest,
        reset_feeds=reset_feeds,
        reset_all=reset_all,
        verbose=verbose,
    ))

    typer.echo(
        f"Synced {result.new_items} new items "
        f"({result.email_count} email, {result.feed_count} feeds). "
        f"{len(result.errors)} errors."
    )
    if result.skipped_unknown_senders:
        typer.echo(
            f"{len(result.skipped_unknown_senders)} unknown senders skipped."
        )


@synthesize_app.command("synthesize")
def synthesize(
    pending: bool = typer.Option(False, "--pending", help="Process pending items (cron mode)"),
    all_items: bool = typer.Option(False, "--all", help="Process all items (ignore wait)"),
    source: Optional[str] = typer.Option(None, "--source", help="Specific source path"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be synthesized"),
    limit: Optional[int] = typer.Option(None, "--limit", help="Max items to process"),
    wiki: Optional[str] = typer.Option(None, help="Wiki directory path"),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Verbose output"),
) -> None:
    """Synthesize wiki pages from pending sources using LLM."""
    import asyncio
    from readpile.core.config import load_config
    from readpile.sync.synthesizer import Synthesizer

    config = load_config()
    wiki_dir = Path(wiki or config.get("wiki", {}).get("default_dir", "")).expanduser()
    if not wiki_dir or not (wiki_dir / ".wiki.toml").exists():
        typer.echo("Error: No wiki found. Run `readpile wiki init` first.", err=True)
        raise typer.Exit(code=1)

    if limit is not None:
        config.setdefault("sync", {})["max_auto_synthesize_per_run"] = limit

    synth = Synthesizer(config, wiki_dir, dry_run=dry_run)

    if source:
        asyncio.run(synth.process_source(source))
    elif all_items:
        asyncio.run(synth.process_all(verbose=verbose))
    else:
        asyncio.run(synth.process_pending(verbose=verbose))


@feeds_app.command("add")
def feeds_add(
    url: str = typer.Argument(..., help="Feed URL to add"),
    name: Optional[str] = typer.Option(None, help="Feed name"),
    kind: Optional[str] = typer.Option(None, help="Feed kind (rss/youtube/podcast)"),
) -> None:
    """Add a feed subscription."""
    import asyncio
    from readpile.core.config import get_config_path
    from readpile.core.detector import detect_url_type, URLType
    from readpile.sync.sources import FeedRegistry, Feed
    from readpile.crawlers.discovery import (
        discover_feed, discover_podcast_feed, resolve_youtube_feed, _ensure_scheme,
    )

    config_dir = get_config_path().parent
    registry = FeedRegistry(
        config_dir / "feeds.toml",
        config_dir / "sync.lock",
    )

    resolved_url = _ensure_scheme(url)
    url_type = detect_url_type(resolved_url)

    detected_kind = kind
    feed_url = resolved_url

    if not detected_kind:
        if url_type == URLType.youtube_channel:
            detected_kind = "youtube"
            result = asyncio.run(resolve_youtube_feed(resolved_url))
            if result:
                feed_url = result
        elif url_type == URLType.rss:
            detected_kind = "rss"
        else:
            podcast_feed = asyncio.run(discover_podcast_feed(resolved_url))
            if podcast_feed:
                detected_kind = "podcast"
                feed_url = podcast_feed
            else:
                rss_feed = asyncio.run(discover_feed(resolved_url))
                if rss_feed:
                    detected_kind = "rss"
                    feed_url = rss_feed
                else:
                    detected_kind = "rss"

    source_name = name or feed_url
    if not name:
        try:
            import feedparser
            feed = feedparser.parse(feed_url)
            if feed.feed.get("title"):
                source_name = feed.feed["title"]
        except Exception:
            pass
        if source_name == feed_url and detected_kind == "youtube":
            try:
                import re
                match = re.search(r"channel_id=([A-Za-z0-9_-]+)", feed_url)
                if match:
                    from readpile.crawlers.discovery import scrape_youtube_channel_videos
                    title, _ = asyncio.run(scrape_youtube_channel_videos(match.group(1)))
                    if title:
                        source_name = title
            except Exception:
                pass

    typer.echo(f"Auto-detected: {detected_kind}")
    typer.echo(f'Name: "{source_name}"')

    new_feed = Feed(name=source_name, url=feed_url, kind=detected_kind)
    registry.load()
    status = registry.add(new_feed)
    if status == "added":
        typer.echo("Added to feeds.toml")
    elif status == "updated":
        typer.echo("Updated existing feed in feeds.toml")
    else:
        typer.echo("Feed already exists and is up to date.")


@feeds_app.command("list")
def feeds_list() -> None:
    """List all configured feed subscriptions."""
    from readpile.core.config import get_config_path
    from readpile.sync.sources import FeedRegistry

    config_dir = get_config_path().parent
    registry = FeedRegistry(config_dir / "feeds.toml")
    feeds = registry.load()

    if not feeds:
        typer.echo("No feeds configured.")
        return

    for i, f in enumerate(feeds, 1):
        status = ""
        if f.disabled:
            status = " [disabled]"
        elif not f.synthesize:
            status = " [no-synth]"
        typer.echo(f"  {i}. {f.name} ({f.kind}) — {f.url}{status}")


@feeds_app.command("remove")
def feeds_remove(
    identifiers: str = typer.Argument(..., help="Feed name or comma/hyphen-separated indices to remove"),
) -> None:
    """Remove feed subscriptions."""
    from readpile.core.config import get_config_path
    from readpile.sync.sources import FeedRegistry

    config_dir = get_config_path().parent
    registry = FeedRegistry(
        config_dir / "feeds.toml",
        config_dir / "sync.lock",
    )
    feeds = registry.load()

    # Parse indices
    indices = set()
    for part in identifiers.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            try:
                start_s, end_s = part.split('-', 1)
                start, end = int(start_s), int(end_s)
                indices.update(range(start, end + 1))
            except ValueError:
                pass
        else:
            try:
                indices.add(int(part))
            except ValueError:
                pass

    valid_indices = {i for i in indices if 1 <= i <= len(feeds)}
    urls_to_remove = []

    if valid_indices:
        for i in sorted(valid_indices):
            urls_to_remove.append(feeds[i - 1].url)
    else:
        # Fallback to name-based match
        matched = [f.url for f in feeds if f.name == identifiers]
        if not matched:
            typer.echo(f"Feed not found: {identifiers}", err=True)
            raise typer.Exit(code=1)
        urls_to_remove.extend(matched)

    for url in urls_to_remove:
        try:
            # Re-load or find feed for message
            feed = next(f for f in feeds if f.url == url)
            registry.remove_by_url(url)
            typer.echo(f"Removed: {feed.name} ({url})")
        except (KeyError, StopIteration):
            pass


@feeds_app.command("enable")
def feeds_enable(
    name: str = typer.Argument(..., help="Feed name to re-enable"),
) -> None:
    """Re-enable a disabled feed subscription."""
    from readpile.core.config import get_config_path
    from readpile.sync.sources import FeedRegistry

    config_dir = get_config_path().parent
    registry = FeedRegistry(
        config_dir / "feeds.toml",
        config_dir / "sync.lock",
    )
    registry.load()
    try:
        registry.enable(name)
        typer.echo(f"Enabled: {name}")
    except KeyError:
        typer.echo(f"Feed not found: {name}", err=True)
        raise typer.Exit(code=1)


@status_app.command("status")
def status(
    wiki: Optional[str] = typer.Option(None, help="Wiki directory path"),
) -> None:
    """Show sync status overview."""
    from readpile.core.config import load_config, get_config_path
    from readpile.sync.state import SyncState
    from readpile.sync.sources import FeedRegistry

    config = load_config()
    config_dir = get_config_path().parent
    state_file = Path(config.get("sync", {}).get(
        "state_file", "~/.readpile/sync-state.json"
    )).expanduser()

    wiki_dir = Path(wiki or config.get("wiki", {}).get("default_dir", "")).expanduser()

    state = SyncState(state_file, wiki_dir=wiki_dir if wiki_dir.exists() else None)
    registry = FeedRegistry(config_dir / "feeds.toml")
    feeds = registry.load()

    last_sync = state._data.get("last_sync", "never")
    pending = state.get_pending()
    history = state.get_digest_history()
    last_digest_items = len(history[-1]["item_map"]) if history else 0

    typer.echo(f"Last sync: {last_sync}")
    typer.echo(f"Pending synthesis: {len(pending)}")
    typer.echo(f"Items in last digest: {last_digest_items}")

    if feeds:
        typer.echo("\nFeed health:")
        for f in feeds:
            feed_key = f.url
            failures = state.get_consecutive_failures(feed_key)
            if f.disabled:
                status_str = "disabled"
            elif failures > 0:
                status_str = f"failing ({failures} consecutive)"
            else:
                status_str = "OK"
            typer.echo(f"  {f.name}: {status_str}")

    if wiki_dir.exists() and (wiki_dir / ".wiki.toml").exists():
        from readpile.wiki import WikiStore
        store = WikiStore(wiki_dir)
        pages = store.list_pages()
        typer.echo(f"\nWiki pages: {len(pages)}")

    log_file = config.get("sync", {}).get("log_file", "~/.readpile/sync.log")
    typer.echo(f"Sync log: {log_file}")
