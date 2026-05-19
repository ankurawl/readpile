"""Sync pipeline — orchestrator for email, feeds, digest."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from readpile.sync.state import SyncState
from readpile.sync.urls import normalize_url

log = logging.getLogger("readpile.sync")


@dataclass
class SyncError:
    url: str
    error: str


@dataclass
class SyncResult:
    new_items: int = 0
    saved_paths: list[Path] = field(default_factory=list)
    errors: list[SyncError] = field(default_factory=list)
    email_count: int = 0
    feed_count: int = 0
    skipped_unknown_senders: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


class SyncPipeline:
    """Async orchestrator: replies → email → feeds → save → digest."""

    def __init__(
        self,
        config: dict,
        wiki_dir: Path,
        dry_run: bool = False,
    ) -> None:
        self.config = config
        self.wiki_dir = Path(wiki_dir).expanduser()
        self.dry_run = dry_run
        self._sync_cfg = config.get("sync", {})

    async def run(
        self,
        no_email: bool = False,
        no_feeds: bool = False,
        no_digest: bool = False,
        reset_feeds: bool = False,
        reset_all: bool = False,
        verbose: bool = False,
    ) -> SyncResult:
        from readpile.sync.logging import setup_logging

        log_file = self._sync_cfg.get("log_file", "~/.readpile/sync.log")
        setup_logging(Path(log_file).expanduser())

        state_file = Path(self._sync_cfg.get(
            "state_file", "~/.readpile/sync-state.json"
        )).expanduser()
        lock_path = state_file.parent / "sync.lock"

        state = SyncState(state_file, wiki_dir=self.wiki_dir)
        state.acquire_lock(lock_path)

        try:
            if reset_all:
                state.reset_all()
                if verbose:
                    log.info("All sync state cleared")
            elif reset_feeds:
                state.reset_feeds()
                if verbose:
                    log.info("Feed state cleared")

            return await self._run_pipeline(state, no_email, no_feeds, no_digest, verbose)
        finally:
            state.release_lock()

    async def _run_pipeline(
        self,
        state: SyncState,
        no_email: bool,
        no_feeds: bool,
        no_digest: bool,
        verbose: bool,
    ) -> SyncResult:
        start = time.monotonic()
        result = SyncResult()

        from readpile.core.config import get_config_path
        from readpile.sync.sources import SourceRegistry
        config_dir = get_config_path().parent
        registry = SourceRegistry(
            config_dir / "sources.toml",
            config_dir / "sync.lock",
        )
        sources = registry.load()

        # 1. Process replies
        if state.shutting_down:
            return result

        email_cfg = self._sync_cfg.get("email", {})
        digest_cfg = self._sync_cfg.get("digest", {})
        email_enabled = email_cfg.get("enabled", False) and not no_email
        provider = None

        if email_enabled:
            try:
                provider = await self._get_email_provider(email_cfg)
                if verbose:
                    log.info("Processing replies...")
                await self._process_replies(provider, state, registry, sources)
                state.commit()
            except Exception as exc:
                log.warning("Email reply processing failed: %s", exc)
                provider = None

        # 2. Check email
        if state.shutting_down:
            return result

        new_items: list[dict] = []

        if email_enabled and provider:
            if verbose:
                log.info("Checking email...")
            try:
                email_items = await self._check_email(provider, state, sources)
                new_items.extend(email_items)
                result.email_count = len(email_items)
                state.commit()
            except Exception as exc:
                log.warning("Email check failed: %s", exc)
                result.errors.append(SyncError("email", str(exc)))

        # 3. Crawl feeds
        if state.shutting_down:
            return result

        if not no_feeds:
            if verbose:
                log.info("Crawling feeds...")
            try:
                feed_items = await self._crawl_feeds(state, sources, registry)
                result.feed_count = len(feed_items)

                for item in feed_items:
                    norm_url = normalize_url(item.get("url", ""))
                    already = any(normalize_url(e.get("url", "")) == norm_url for e in new_items)
                    if not already:
                        new_items.append(item)

                state.commit()
            except Exception as exc:
                log.warning("Feed crawling failed: %s", exc)
                result.errors.append(SyncError("feeds", str(exc)))

        # 4. Save to wiki
        if state.shutting_down:
            return result

        if not self.dry_run:
            for item in new_items:
                try:
                    path = await self._save_item(item, state)
                    if path:
                        result.saved_paths.append(path)
                        result.new_items += 1
                except Exception as exc:
                    url = item.get("url", "unknown")
                    log.warning("Failed to save %s: %s", url, exc)
                    result.errors.append(SyncError(url, str(exc)))
            state.commit()
        else:
            result.new_items = len(new_items)

        # 5. Send digest
        if state.shutting_down:
            return result

        if not no_digest and digest_cfg.get("enabled", False) and new_items and not self.dry_run:
            if verbose:
                log.info("Sending digest...")
            try:
                await self._send_digest(new_items, state, result)
            except Exception as exc:
                log.warning("Digest failed: %s", exc)
                result.errors.append(SyncError("digest", str(exc)))

        state.commit()
        result.duration_seconds = time.monotonic() - start
        return result

    async def _get_email_provider(self, email_cfg: dict):
        from readpile.sync.email.gmail import GmailProvider
        creds_file = Path(email_cfg.get(
            "credentials_file", "~/.readpile/email-credentials.json"
        )).expanduser()
        provider = GmailProvider(creds_file)
        await provider.connect()
        return provider

    async def _process_replies(
        self, provider, state: SyncState, registry, sources,
    ):
        from readpile.sync.reply import (
            ReplyProcessor, SynthesizeAction, SkipAction,
            AddSourceAction, RemoveSourceAction,
        )
        from readpile.sync.sources import Source

        processor = ReplyProcessor(self.config)
        actions = await processor.process(provider, state)

        for action in actions:
            if isinstance(action, SynthesizeAction):
                for path in action.source_paths:
                    state.mark_pending(path)
                    log.info("Marked for synthesis: %s", path)
            elif isinstance(action, SkipAction):
                for path in action.source_paths:
                    state.mark_skipped(path)
                    log.info("Marked as skipped: %s", path)
            elif isinstance(action, AddSourceAction):
                source = Source(
                    name=action.name or action.url,
                    url=action.url,
                    kind=action.kind,
                )
                registry.add(source)
                log.info("Added source: %s", action.url)
            elif isinstance(action, RemoveSourceAction):
                try:
                    registry.remove(action.name)
                    log.info("Removed source: %s", action.name)
                except KeyError:
                    log.warning("Source not found for removal: %s", action.name)

    async def _check_email(
        self, provider, state: SyncState, sources,
    ) -> list[dict]:
        from readpile.sync.email.extract import extract_content

        since = datetime.now(timezone.utc) - timedelta(
            days=self._sync_cfg.get("email", {}).get("max_age_days", 7)
        )
        labels = self._sync_cfg.get("email", {}).get("labels", ["INBOX"])

        messages = await provider.fetch_messages(labels, since)

        items: list[dict] = []
        for msg in messages:
            if state.is_email_seen(msg.message_id):
                continue
            state.mark_email_seen(msg.message_id)

            status, extracted = extract_content(msg, sources, self.config)
            if status.startswith("skipped:unknown"):
                log.info("Unknown sender skipped: %s", msg.sender)
            for item_data in extracted:
                item_data["source_type"] = "email"
                items.append(item_data)

        return items

    async def _crawl_feeds(
        self, state: SyncState, sources, registry,
    ) -> list[dict]:
        from readpile.sync.feeds import FeedProcessor

        processor = FeedProcessor(sources, state, self.config, registry)
        results = await processor.check_all()

        items: list[dict] = []
        for r in results:
            norm = normalize_url(r.url)
            if state.is_saved_url(norm):
                continue

            items.append({
                "url": r.url,
                "title": r.title,
                "content_type": r.content_type,
                "date": r.date,
                "author": r.author,
                "source_type": "feed",
                "source_name": r.source.name,
                "skip_synthesis": not r.source.synthesize,
            })

        return items

    async def _save_item(self, item: dict, state: SyncState) -> Path | None:
        url = item.get("url", "")
        norm = normalize_url(url)

        if state.is_saved_url(norm):
            return None

        from readpile.wiki import WikiStore
        from readpile.core.models import ContentItem, ContentType

        kind = item.get("kind", "")
        ct_str = item.get("content_type", "article")

        content = item.get("content", "")

        if kind == "newsletter" and "html" in item:
            try:
                from readpile.scrapers.article import scrape_article
                ci = await asyncio.to_thread(
                    scrape_article, url, item["html"],
                )
                content = ci.text
            except Exception as exc:
                log.warning("Newsletter scrape failed: %s", exc)
                content = item.get("html", "")
        elif kind == "url" and url:
            try:
                from readpile.scrapers import scrape_url
                ci = await scrape_url(url)
                content = ci.text
                if not item.get("title"):
                    item["title"] = ci.title
            except Exception as exc:
                log.warning("URL scrape failed for %s: %s", url, exc)
                return None

        if not content:
            return None

        try:
            ct = ContentType(ct_str)
        except ValueError:
            ct = ContentType.article

        from datetime import date as date_cls
        date_val = None
        if item.get("date"):
            try:
                date_val = date_cls.fromisoformat(str(item["date"])[:10])
            except (ValueError, TypeError):
                pass

        ci = ContentItem(
            text=content,
            title=item.get("title", "Untitled"),
            source_url=url,
            content_type=ct,
            date=date_val,
            author=item.get("author"),
        )

        store = WikiStore(self.wiki_dir)
        path = await asyncio.to_thread(store.save_source_from_item, ci)

        state.mark_saved_url(url)
        state.mark_pending(str(path))

        if item.get("skip_synthesis", False):
            state.mark_skipped(str(path))

        item["source_path"] = str(path)
        item["word_count"] = ci.word_count
        item["preview"] = content[:200] if content else ""

        return path

    async def _send_digest(
        self, items: list[dict], state: SyncState, result: SyncResult,
    ):
        from readpile.sync.digest import DigestBuilder, DigestSender

        builder = DigestBuilder(self.config)
        body, files = builder.build(
            items, state,
            skipped_unknown_senders=result.skipped_unknown_senders,
            errors=[f"{e.url}: {e.error}" for e in result.errors],
        )

        if not body:
            return

        digest_cfg = self._sync_cfg.get("digest", {})
        to_addr = digest_cfg.get("to", "")
        if not to_addr:
            return

        from datetime import date
        subject = f"readpile — {date.today().isoformat()} ({len(items)} new items)"

        sender = DigestSender(self.config)
        sender.send(subject, body, files, to_addr)
