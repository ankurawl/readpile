"""Feed processor — crawl feeds with state filtering and rate limiting."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from readpile.crawlers import discovery as _discovery
from readpile.crawlers import rss as _rss
from readpile.sync.sources import Feed, FeedRegistry
from readpile.sync.state import SyncState

log = logging.getLogger("readpile.sync")


@dataclass
class FeedResult:
    """A single discovered feed entry."""

    source: Feed
    url: str
    title: str
    content_type: str
    date: str | None = None
    author: str | None = None
    content: str | None = None
    word_count: int = 0


class FeedProcessor:
    """Crawl configured feeds, filter by state, rate-limit per domain."""

    def __init__(
        self,
        feeds: list[Feed],
        state: SyncState,
        config: dict,
        registry: FeedRegistry | None = None,
    ) -> None:
        self.feeds = feeds
        self.state = state
        self.config = config
        self.registry = registry
        self._rate_limit = config.get("scrape", {}).get("rate_limit", 1.0)
        self._max_initial = config.get("sync", {}).get("max_initial_entries", 20)
        self._max_failures = config.get("sync", {}).get("max_consecutive_failures", 7)
        self._last_request: dict[str, float] = {}

    async def _throttle(self, url: str) -> None:
        domain = urlparse(url).netloc
        import time
        now = time.monotonic()
        last = self._last_request.get(domain, 0)
        wait = self._rate_limit - (now - last)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request[domain] = time.monotonic()

    async def check_all(self) -> list[FeedResult]:
        results: list[FeedResult] = []
        for feed in self.feeds:
            if feed.disabled:
                continue
            try:
                items = await self.check_feed(feed)
                results.extend(items)
                self.state.reset_failures(feed.url)
            except Exception as exc:
                count = self.state.increment_failure(feed.url)
                log.warning("Feed %s failed (%d/%d): %s", feed.name, count, self._max_failures, exc)
                if count >= self._max_failures and self.registry:
                    try:
                        self.registry.disable(feed.name)
                        log.warning("Auto-disabled feed %s after %d failures", feed.name, count)
                    except Exception:
                        pass
        return results

    async def check_feed(self, feed: Feed) -> list[FeedResult]:
        feed_url = feed.url

        if feed.kind == "youtube":
            resolved = await _discovery.resolve_youtube_feed(feed_url)
            if resolved:
                feed_url = resolved

        feed_info, entries = await asyncio.to_thread(
            _rss.crawl_rss_detailed, feed_url, None,
        )

        actual_url = feed_info.get("href") or feed_info.get("feed_url", "")
        if actual_url and actual_url != feed.url and self.registry:
            try:
                self.registry.update_url(feed.name, actual_url)
                log.info("Feed %s redirected, updated URL: %s", feed.name, actual_url)
            except Exception:
                pass

        seen_urls = self.state.get_feed_seen_urls(feed.url)
        is_first_sync = len(seen_urls) == 0

        if is_first_sync and len(entries) > self._max_initial:
            for entry in entries[self._max_initial:]:
                entry_url = entry.get("url", "")
                if entry_url:
                    self.state.mark_url_seen(entry_url, feed.url)
            entries = entries[:self._max_initial]

        results: list[FeedResult] = []
        for entry in entries:
            entry_url = entry.get("url", "")
            if not entry_url:
                continue
            if self.state.is_url_seen(entry_url, feed.url):
                continue

            self.state.mark_url_seen(entry_url, feed.url)

            ct = "article"
            if feed.kind == "youtube":
                ct = "youtube"
            elif feed.kind == "podcast":
                ct = "podcast"

            results.append(FeedResult(
                source=feed,
                url=entry_url,
                title=entry.get("title", ""),
                content_type=ct,
                date=entry.get("published"),
                author=entry.get("author"),
            ))

        return results

    async def scrape_result(self, result: FeedResult) -> FeedResult:
        """Scrape/transcribe content for a feed result."""
        await self._throttle(result.url)

        try:
            if result.content_type == "youtube":
                from readpile.transcribers.youtube import transcribe_youtube
                item = await asyncio.to_thread(transcribe_youtube, result.url)
                result.content = item.text
                result.title = result.title or item.title
                result.word_count = item.word_count
            elif result.content_type == "podcast":
                from readpile.crawlers.discovery import _ensure_scheme
                from readpile.core.detector import detect_url_type, URLType
                url_type = detect_url_type(result.url)
                if url_type == URLType.youtube:
                    from readpile.transcribers.youtube import transcribe_youtube
                    item = await asyncio.to_thread(transcribe_youtube, result.url)
                    result.content = item.text
                    result.word_count = item.word_count
                else:
                    from readpile.scrapers import scrape_url
                    item = await scrape_url(result.url)
                    result.content = item.text
                    result.word_count = item.word_count
            else:
                from readpile.scrapers import scrape_url
                item = await scrape_url(result.url)
                result.content = item.text
                result.title = result.title or item.title
                result.word_count = item.word_count
        except Exception as exc:
            log.warning("Failed to scrape %s: %s", result.url, exc)
            await asyncio.sleep(5)
            try:
                from readpile.scrapers import scrape_url
                item = await scrape_url(result.url)
                result.content = item.text
                result.word_count = item.word_count
            except Exception as retry_exc:
                log.error("Retry also failed for %s: %s", result.url, retry_exc)

        return result
