"""Synthesizer — LLM-powered wiki page creation from pending sources."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from readpile.sync.state import SyncState

log = logging.getLogger("readpile.sync")


class Synthesizer:
    """LLM-powered wiki synthesis from pending sources."""

    def __init__(
        self,
        config: dict,
        wiki_dir: Path,
        dry_run: bool = False,
    ) -> None:
        self.config = config
        self.wiki_dir = Path(wiki_dir).expanduser()
        self.dry_run = dry_run
        sync_cfg = config.get("sync", {})
        self._wait_days = sync_cfg.get("synthesis_wait_days", 7)
        self._window_days = sync_cfg.get("synthesis_window_days", 90)
        self._max_per_run = sync_cfg.get("max_auto_synthesize_per_run", 20)

    async def process_pending(self, verbose: bool = False) -> None:
        from readpile.sync.logging import setup_logging
        log_file = self.config.get("sync", {}).get("log_file", "~/.readpile/sync.log")
        setup_logging(Path(log_file).expanduser())

        state_file = Path(self.config.get("sync", {}).get(
            "state_file", "~/.readpile/sync-state.json"
        )).expanduser()
        lock_path = state_file.parent / "sync.lock"

        state = SyncState(state_file, wiki_dir=self.wiki_dir)
        state.acquire_lock(lock_path)

        try:
            now = datetime.now(timezone.utc)
            cutoff = (now - timedelta(days=self._window_days)).isoformat()
            wait_cutoff = (now - timedelta(days=self._wait_days)).isoformat()

            pending = state.get_pending()
            skipped = state.get_skipped()

            to_synthesize: list[tuple[str, str]] = []

            for path, ts in pending.items():
                if ts < cutoff:
                    continue
                if path in skipped:
                    continue
                if ts <= wait_cutoff:
                    to_synthesize.append((path, ts))

            to_synthesize.sort(key=lambda x: x[1])

            if len(to_synthesize) > self._max_per_run:
                to_synthesize = to_synthesize[:self._max_per_run]

            if verbose:
                log.info("Processing %d pending items for synthesis", len(to_synthesize))

            for i, (path, _) in enumerate(to_synthesize, 1):
                if verbose:
                    log.info("Synthesizing item %d/%d: %s", i, len(to_synthesize), path)
                if not self.dry_run:
                    await self._synthesize_source(path, state)
                else:
                    log.info("  [dry-run] Would synthesize: %s", path)

            state.commit()
        finally:
            state.release_lock()

    async def process_all(self, verbose: bool = False) -> None:
        from readpile.sync.logging import setup_logging
        log_file = self.config.get("sync", {}).get("log_file", "~/.readpile/sync.log")
        setup_logging(Path(log_file).expanduser())

        state_file = Path(self.config.get("sync", {}).get(
            "state_file", "~/.readpile/sync-state.json"
        )).expanduser()
        lock_path = state_file.parent / "sync.lock"

        state = SyncState(state_file, wiki_dir=self.wiki_dir)
        state.acquire_lock(lock_path)

        try:
            now = datetime.now(timezone.utc)
            cutoff = (now - timedelta(days=self._window_days)).isoformat()

            pending = state.get_pending()
            skipped = state.get_skipped()

            to_synthesize: list[tuple[str, str]] = []
            for path, ts in pending.items():
                if ts < cutoff:
                    continue
                if path in skipped:
                    continue
                to_synthesize.append((path, ts))

            to_synthesize.sort(key=lambda x: x[1])

            if len(to_synthesize) > self._max_per_run:
                to_synthesize = to_synthesize[:self._max_per_run]

            if verbose:
                log.info("Processing %d items for synthesis (--all)", len(to_synthesize))

            for i, (path, _) in enumerate(to_synthesize, 1):
                if verbose:
                    log.info("Synthesizing item %d/%d: %s", i, len(to_synthesize), path)
                if not self.dry_run:
                    await self._synthesize_source(path, state)
                else:
                    log.info("  [dry-run] Would synthesize: %s", path)

            state.commit()
        finally:
            state.release_lock()

    async def process_source(self, source_path: str) -> None:
        from readpile.sync.logging import setup_logging
        log_file = self.config.get("sync", {}).get("log_file", "~/.readpile/sync.log")
        setup_logging(Path(log_file).expanduser())

        state_file = Path(self.config.get("sync", {}).get(
            "state_file", "~/.readpile/sync-state.json"
        )).expanduser()
        lock_path = state_file.parent / "sync.lock"

        state = SyncState(state_file, wiki_dir=self.wiki_dir)
        state.acquire_lock(lock_path)

        try:
            await self._synthesize_source(source_path, state)
            state.commit()
        finally:
            state.release_lock()

    async def _synthesize_source(self, source_path: str, state: SyncState) -> None:
        from readpile.wiki import WikiStore
        from readpile.sync.llm import generate

        store = WikiStore(self.wiki_dir)

        try:
            source_content = await asyncio.to_thread(store.read_page, source_path)
        except FileNotFoundError:
            log.warning("Source not found: %s", source_path)
            state.mark_synthesis_failed(source_path, "Source file not found")
            return

        title_match = re.search(r'^title:\s*"?(.+?)"?\s*$', source_content, re.MULTILINE)
        source_title = title_match.group(1) if title_match else "Untitled"

        key_terms = " ".join(source_title.split()[:10])
        first_500 = " ".join(source_content.split()[:500])
        search_query = key_terms

        try:
            search_results = await asyncio.to_thread(store.search, search_query, "pages")
        except Exception:
            search_results = []

        related_pages: list[dict] = []
        related_contents: list[str] = []
        for r in search_results[:5]:
            try:
                page_content = await asyncio.to_thread(store.read_page, r["name"])
                related_pages.append(r)
                related_contents.append(page_content)
            except Exception:
                continue

        related_context = ""
        for page, content in zip(related_pages, related_contents):
            related_context += f"\n\n--- Existing page: {page['name']} ---\n{content[:3000]}"

        system_prompt = """You are a wiki synthesis engine. Given source content and existing related wiki pages, decide:
1. If the source contains genuinely new information → create a new wiki page or update an existing one
2. If the source is redundant (covered by existing pages) → respond with SKIP
3. If the source contradicts existing pages → update with both viewpoints

IMPORTANT RULES:
- If creating/updating, respond with the full page content including YAML frontmatter
- Frontmatter MUST include: title, category, tags, sources, related, source_date, ingested, updated
- category must be one of: concept, entity, summary, comparison, exploration, reference
- Use [[wikilinks]] to link to related pages
- If redundant, respond with exactly: SKIP: <reason>
- Keep pages concise (3-5 paragraphs max with key takeaways)"""

        user_prompt = f"""Source content:
{source_content[:5000]}

Related existing pages:
{related_context if related_context else '(no related pages found)'}

Analyze this source and either create/update a wiki page or skip if redundant."""

        try:
            response = generate(system_prompt, user_prompt, self.config)
        except Exception as exc:
            log.error("LLM call failed for %s: %s", source_path, exc)
            state.mark_synthesis_failed(source_path, f"LLM error: {exc}")
            return

        if response.strip().startswith("SKIP"):
            reason = response.strip().removeprefix("SKIP:").strip()
            log.info("Skipped %s: %s", source_path, reason or "no incremental value")
            state.mark_synthesized(source_path)
            await asyncio.to_thread(
                store.append_log,
                f"synthesize | skip | {source_title} | {reason or 'no incremental value'}",
            )
            return

        page_content = response.strip()
        if page_content.startswith("```"):
            page_content = page_content.split("\n", 1)[1].rsplit("```", 1)[0]

        page_title_match = re.search(r'^title:\s*"?(.+?)"?\s*$', page_content, re.MULTILINE)
        page_title = page_title_match.group(1) if page_title_match else source_title

        slug = self._make_slug(page_title)

        existing_slugs = {r["name"] for r in related_pages}
        page_path = store.pages_dir / f"{slug}.md"
        if page_path.exists() and slug not in existing_slugs:
            date_match = re.search(r'(\d{4}-\d{2})', source_path)
            suffix = date_match.group(1) if date_match else hashlib.md5(source_path.encode()).hexdigest()[:8]
            slug = f"{slug}-{suffix}"

        try:
            await asyncio.to_thread(store.write_page, slug, page_content)
            state.mark_synthesized(source_path)
            log.info("Created/updated page: %s", slug)
            await asyncio.to_thread(
                store.append_log,
                f"synthesize | write | {page_title} | {source_path}",
            )
        except ValueError as exc:
            repaired = self._repair_frontmatter(page_content)
            if repaired:
                try:
                    await asyncio.to_thread(store.write_page, slug, repaired)
                    state.mark_synthesized(source_path)
                    log.info("Created page (after repair): %s", slug)
                    return
                except Exception:
                    pass
            log.error("Synthesis failed for %s: %s", source_path, exc)
            state.mark_synthesis_failed(source_path, str(exc))

    def _make_slug(self, title: str) -> str:
        name = title.lower()
        name = re.sub(r"[^a-z0-9 \-]", "", name)
        name = re.sub(r"[\s_]+", "-", name)
        name = re.sub(r"-+", "-", name)
        name = name.strip("-")
        name = name[:80].rstrip("-")
        if not name:
            name = f"page-{hashlib.md5(title.encode()).hexdigest()[:8]}"
        return name

    def _repair_frontmatter(self, content: str) -> str | None:
        try:
            if not content.startswith("---"):
                return None
            end = content.index("---", 3)
            fm = content[3:end]
            body = content[end + 3:]

            lines = []
            for line in fm.strip().splitlines():
                if ":" in line:
                    key, _, val = line.partition(":")
                    val = val.strip()
                    if key.strip() == "title" and not val.startswith('"'):
                        val = f'"{val}"'
                    lines.append(f"{key.strip()}: {val}")
                else:
                    lines.append(line)

            return "---\n" + "\n".join(lines) + "\n---" + body
        except Exception:
            return None
