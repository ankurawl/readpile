"""MCP server — expose readpile's library tools via Model Context Protocol."""

from __future__ import annotations


def _create_server():
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("readpile")

    def _ensure_scheme(url: str) -> str:
        if url and not url.startswith(("http://", "https://")):
            return "https://" + url
        return url

    @mcp.tool()
    async def scrape(url: str) -> str:
        """Scrape a URL and return its content as YAML front matter + markdown.

        Tries structured article extraction first, falls back to generic
        webpage scraping if the article is too short or missing.
        """
        try:
            from readpile.scrapers import scrape_url
            item = await scrape_url(_ensure_scheme(url))
            return item.to_stdout()
        except SystemExit as e:
            return str(e)

    @mcp.tool()
    async def transcribe(
        source: str,
        language: str = "en",
        fallback_url: str | None = None,
    ) -> str:
        """Transcribe audio/video content from a URL.

        Supports YouTube URLs, direct audio/video URLs, and blog/webpage URLs
        that contain embedded YouTube videos or audio players.

        Args:
            source: URL to transcribe (YouTube, audio/video file, or webpage).
            language: Language code for transcription (default: "en").
            fallback_url: Optional webpage URL to check for embedded YouTube
                videos if the primary source fails. Useful for podcast episodes
                where the audio URL requires ffmpeg but the episode webpage has
                an embedded YouTube player.

        Returns YAML front matter + markdown transcript.
        """
        try:
            from readpile.core.detector import detect_url_type, URLType

            resolved = _ensure_scheme(source)
            url_type = detect_url_type(resolved)

            if url_type == URLType.youtube:
                from readpile.transcribers.youtube import transcribe_youtube
                item = transcribe_youtube(resolved, language)
                return item.to_stdout()

            if url_type in (URLType.audio_file, URLType.video):
                if "://" not in source:
                    return "Error: local file paths are not supported. Provide a URL."
                try:
                    from readpile.transcribers.audio import transcribe_from_url
                    item = transcribe_from_url(resolved)
                    return item.to_stdout()
                except SystemExit:
                    if fallback_url:
                        result = await _transcribe_via_fallback(
                            _ensure_scheme(fallback_url), language
                        )
                        if result:
                            return result
                    return (
                        "Error: Audio transcription requires ffmpeg and whisper, "
                        "which are not installed. Alternatives:\n"
                        "- Provide the episode's webpage URL instead (if it has "
                        "an embedded YouTube video, transcription works without ffmpeg)\n"
                        "- Use fallback_url parameter with the episode webpage URL\n"
                        "- Install ffmpeg: brew install ffmpeg"
                    )

            if url_type in (URLType.blog, URLType.website):
                media_url = await _extract_media_url(resolved)
                if media_url:
                    media_type = detect_url_type(media_url)
                    if media_type == URLType.youtube:
                        from readpile.transcribers.youtube import transcribe_youtube
                        item = transcribe_youtube(media_url, language)
                        return item.to_stdout()
                    if media_type in (URLType.audio_file, URLType.video):
                        try:
                            from readpile.transcribers.audio import transcribe_from_url
                            item = transcribe_from_url(media_url)
                            return item.to_stdout()
                        except SystemExit:
                            return (
                                f"Error: Found audio at {media_url} but ffmpeg is "
                                "not installed. Install: brew install ffmpeg"
                            )
                return (
                    f"Error: No embedded YouTube video or audio found at {resolved}. "
                    "Try providing a direct YouTube or audio URL instead."
                )

            if url_type == URLType.youtube_channel:
                return (
                    "Error: This is a YouTube channel URL, not a single video. "
                    "Use crawl(url, mode='youtube') to discover video URLs first, "
                    "then transcribe individual videos."
                )

            return (
                f"Error: URL type '{url_type.value}' is not transcribable. "
                "Supported types: youtube, audio_file, video, or a webpage with embedded media."
            )
        except SystemExit as e:
            return str(e)

    @mcp.tool()
    async def crawl(
        url: str,
        mode: str = "auto",
        recent: int | None = None,
        limit: int | None = None,
        metadata: bool = False,
    ) -> list[str]:
        """Discover content URLs from a website, blog, or RSS feed.

        Args:
            url: URL to crawl.
            mode: Crawl mode — "auto", "rss", "blog", "site", "podcast", or "youtube".
            recent: Only return N most recent items (RSS/podcast/youtube modes).
            limit: Max pages/posts to discover (blog/site modes).
            metadata: When True (RSS/podcast/youtube modes only), return JSON metadata
                per entry instead of bare URLs. Includes title, date, author,
                description, audio_url, and duration. Ignored for blog/site modes.

        The "podcast" mode auto-discovers the podcast RSS feed from a URL,
        filters to audio-only entries, and always returns metadata.

        The "youtube" mode resolves a YouTube channel URL (@handle, /channel/ID)
        to its RSS feed and returns the most recent videos (up to 15).

        Returns a list of discovered URLs, or JSON metadata strings when
        metadata is enabled.
        """
        try:
            import asyncio
            import json
            from readpile.cli.crawl import _crawl_rss, _detect_crawl_mode

            resolved_url = _ensure_scheme(url)
            effective_mode = mode
            if effective_mode == "auto":
                effective_mode = _detect_crawl_mode(resolved_url)

            is_podcast = effective_mode == "podcast"
            use_metadata = metadata or is_podcast

            if use_metadata and recent is None:
                recent = 50

            if effective_mode == "rss":
                from readpile.core.detector import detect_url_type, URLType
                feed_url = resolved_url
                if detect_url_type(resolved_url) != URLType.rss:
                    discovered = await _discover_feed(resolved_url)
                    if discovered:
                        feed_url = discovered

                if not use_metadata:
                    return await asyncio.to_thread(_crawl_rss, feed_url, recent)

                from readpile.crawlers.rss import crawl_rss_detailed
                feed_info, entries = await asyncio.to_thread(
                    crawl_rss_detailed, feed_url, recent
                )
                result = [json.dumps(feed_info, ensure_ascii=False)]
                result.extend(json.dumps(e, ensure_ascii=False) for e in entries)
                return result

            if is_podcast:
                feed_url = await _discover_podcast_feed(resolved_url)
                if feed_url is None:
                    return [
                        f"Error: No podcast RSS feed found at {resolved_url}. "
                        "Try providing the direct feed URL with mode='rss'."
                    ]
                from readpile.crawlers.rss import crawl_rss_detailed
                feed_info, entries = await asyncio.to_thread(
                    crawl_rss_detailed, feed_url, recent, True
                )
                if not entries:
                    return [
                        f"Error: RSS feed at {feed_url} has no podcast episodes "
                        "(0 audio entries found)."
                    ]
                result = [json.dumps(feed_info, ensure_ascii=False)]
                result.extend(json.dumps(e, ensure_ascii=False) for e in entries)
                return result

            if effective_mode == "blog":
                return await _mcp_crawl_blog(resolved_url, max_pages=limit or 100)
            elif effective_mode == "site":
                return await _mcp_crawl_site(resolved_url, max_pages=limit or 100)
            elif effective_mode == "youtube":
                feed_url = await _resolve_youtube_channel_feed(resolved_url)
                if feed_url is None:
                    return [
                        f"Error: Could not resolve YouTube channel ID from {resolved_url}. "
                        "Try providing the channel's RSS feed URL directly."
                    ]
                if recent is None:
                    recent = 15
                from readpile.crawlers.rss import crawl_rss_detailed
                feed_info, entries = await asyncio.to_thread(
                    crawl_rss_detailed, feed_url, recent
                )
                if use_metadata:
                    result = [json.dumps(feed_info, ensure_ascii=False)]
                    result.extend(json.dumps(e, ensure_ascii=False) for e in entries)
                    return result
                return [e["url"] for e in entries if e.get("url")]
            else:
                return [f"Error: Unknown mode '{effective_mode}'. Use: auto, rss, blog, site, podcast, youtube."]
        except SystemExit as e:
            return [str(e)]

    def _resolve_archive_dir(specified_dir: str | None = None) -> Path:
        """Resolve the archive output directory, with automatic fallback.

        Tries the specified or configured directory first. If it can't be
        created (e.g., home directory not writable in a sandbox), falls back
        to ``./readpile-output/`` relative to the current working directory.
        """
        from pathlib import Path
        from readpile.core.config import load_config

        if specified_dir is not None:
            target = Path(specified_dir).expanduser()
        else:
            config = load_config()
            target = Path(
                config.get("general", {}).get("output_dir", "~/readpile-output")
            ).expanduser()

        try:
            target.mkdir(parents=True, exist_ok=True)
            return target
        except (PermissionError, OSError):
            fallback = Path("readpile-output").resolve()
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback

    @mcp.tool()
    def archive(
        content: str,
        title: str,
        source_url: str,
        content_type: str = "article",
        date: str | None = None,
        author: str | None = None,
        dir: str | None = None,
    ) -> str:
        """Save content to your library as a markdown file with YAML front matter.

        Args:
            content: The text content to save.
            title: Title for the content.
            source_url: Original source URL.
            content_type: One of: article, youtube, audio, podcast, webpage.
            date: Publish date in YYYY-MM-DD format (used in filename). Defaults to today.
            author: Author name (included in filename and metadata).
            dir: Library directory (default: ~/readpile-output or config value).

        Returns the path to the saved file.
        """
        try:
            from pathlib import Path
            from readpile.core.models import ContentItem, ContentType
            from readpile.core.archiver import Archiver

            try:
                ct = ContentType(content_type)
            except ValueError:
                valid = ", ".join(t.value for t in ContentType)
                return f"Error: invalid content_type '{content_type}'. Valid options: {valid}"

            date_val = None
            if date is not None:
                from datetime import date as date_type
                try:
                    date_val = date_type.fromisoformat(date)
                except ValueError:
                    return f"Error: invalid date '{date}'. Use YYYY-MM-DD format."

            item = ContentItem(
                text=content,
                title=title,
                source_url=source_url,
                content_type=ct,
                date=date_val,
                author=author,
            )

            output_dir = _resolve_archive_dir(dir)
            archiver = Archiver(output_dir)
            saved_path = archiver.save(item)
            return str(saved_path)
        except SystemExit as e:
            return str(e)

    @mcp.tool()
    def detect_type(url: str) -> str:
        """Detect the content type of a URL.

        Returns one of: youtube, video, rss, audio_file, local_file, blog, website.
        """
        try:
            from readpile.core.detector import detect_url_type
            return detect_url_type(url).value
        except SystemExit as e:
            return str(e)

    @mcp.tool()
    async def batch_scrape(
        urls: list[str],
        concurrency: int = 3,
        archive_dir: str | None = None,
    ) -> str:
        """Scrape multiple URLs in one call with concurrency control.

        Args:
            urls: List of URLs to scrape.
            concurrency: Max concurrent scrapes (default 3).
            archive_dir: Optional directory to save scraped content. Each
                successfully scraped article is automatically archived as a
                Markdown file, avoiding the need to call archive() per item.

        Returns all scraped content concatenated with ---CONTENT_ITEM---
        delimiters. Failed URLs are included as error items. When archive_dir
        is set, saved file paths are appended after the content.
        """
        if not urls:
            return "No URLs provided."

        import asyncio
        from readpile.scrapers import scrape_url
        from readpile.core.models import ContentItem, ContentType

        sem = asyncio.Semaphore(concurrency)

        async def _scrape_one(u: str) -> ContentItem:
            resolved = _ensure_scheme(u)
            async with sem:
                try:
                    return await asyncio.wait_for(scrape_url(resolved), timeout=60)
                except Exception as exc:
                    return ContentItem(
                        text=f"Error: {exc}",
                        title=f"Failed: {resolved}",
                        source_url=resolved,
                        content_type=ContentType.webpage,
                    )

        items = await asyncio.gather(*[_scrape_one(u) for u in urls])
        result = ContentItem.to_batch(list(items))

        if archive_dir:
            from readpile.core.archiver import Archiver

            output_path = _resolve_archive_dir(archive_dir)
            archiver = Archiver(output_path)
            saved: list[str] = []
            for item in items:
                if not item.title.startswith("Failed:"):
                    try:
                        path = archiver.save(item)
                        saved.append(f"Saved: {path}")
                    except Exception as exc:
                        saved.append(f"Error saving {item.source_url}: {exc}")
            if saved:
                result += "\n\n---ARCHIVED---\n" + "\n".join(saved)

        return result

    # ------------------------------------------------------------------
    # Wiki tools
    # ------------------------------------------------------------------

    def _resolve_wiki_dir(wiki_dir: str | None, require_existing: bool = True) -> "Path":
        from pathlib import Path
        from readpile.core.config import load_config

        if wiki_dir is not None:
            resolved = Path(wiki_dir).expanduser().resolve()
        else:
            config = load_config()
            default = config.get("wiki", {}).get("default_dir", "")
            if not default:
                raise ValueError(
                    "No wiki directory specified. Pass wiki_dir or set "
                    "[wiki] default_dir in ~/.readpile/config.toml"
                )
            resolved = Path(default).expanduser().resolve()

        if require_existing:
            if not (resolved / ".wiki.toml").exists():
                raise FileNotFoundError(
                    f"No wiki found at {resolved}. Run wiki_init to create one."
                )

        return resolved

    @mcp.tool()
    def wiki_init(
        path: str,
        name: str,
        description: str = "",
        categories: list[str] | None = None,
    ) -> str:
        """Create a new wiki with directory structure, config, and conventions file.

        Args:
            path: Directory path for the new wiki.
            name: Wiki name (used in index header).
            description: Short description of the wiki's purpose.
            categories: Page categories (default: concept, entity, summary,
                comparison, exploration, reference).

        Returns confirmation with the conventions file content so the LLM
        has the ingest recipe immediately.
        """
        try:
            from readpile.wiki import WikiStore

            store = WikiStore(path)
            wiki_path = store.init(name, description, categories)
            conventions = store.load_conventions()
            return (
                f"Wiki created at {wiki_path}\n\n"
                f"Customize wiki-conventions.md to adjust LLM behavior.\n\n"
                f"--- Conventions ---\n{conventions}"
            )
        except FileExistsError as e:
            return f"Error: {e}"

    @mcp.tool()
    def wiki_save_source(
        content: str,
        title: str,
        source_url: str,
        content_type: str = "article",
        date: str | None = None,
        author: str | None = None,
        wiki_dir: str | None = None,
    ) -> str:
        """Save raw content to the wiki's sources/ directory.

        For the full ingest workflow, read the wiki conventions first via
        wiki_read('conventions').

        Args:
            content: The text content to save.
            title: Title for the content.
            source_url: Original source URL.
            content_type: One of: article, youtube, audio, podcast, webpage.
            date: Publish date in YYYY-MM-DD format.
            author: Author name.
            wiki_dir: Wiki directory (default: config value).

        Returns the path to the saved source file.
        """
        try:
            from readpile.wiki import WikiStore

            resolved = _resolve_wiki_dir(wiki_dir)
            store = WikiStore(resolved)
            path = store.save_source(content, title, source_url, content_type, date, author)
            return str(path)
        except (ValueError, FileNotFoundError) as e:
            return f"Error: {e}"

    @mcp.tool()
    def wiki_read(
        page: str,
        wiki_dir: str | None = None,
    ) -> str:
        """Read a wiki page, source, or special file by name.

        Supports special names: "index" (auto-generated catalog), "log"
        (operation timeline), "conventions" (behavioral playbook).
        Supports sources/ paths: wiki_read("sources/2026-05-10_article-name")
        reads from the sources directory.

        Args:
            page: Page name (without .md), or "index", "log", "conventions",
                or "sources/filename".
            wiki_dir: Wiki directory (default: config value).

        Returns the page content as markdown.
        """
        try:
            from readpile.wiki import WikiStore

            resolved = _resolve_wiki_dir(wiki_dir)
            store = WikiStore(resolved)
            return store.read_page(page)
        except FileNotFoundError as e:
            pages = []
            try:
                from readpile.wiki import WikiStore as WS
                s = WS(_resolve_wiki_dir(wiki_dir))
                pages = [p["name"] for p in s.list_pages()]
            except Exception:
                pass
            page_list = ", ".join(pages) if pages else "none"
            return f"Error: {e}\nAvailable pages: {page_list}"
        except (ValueError,) as e:
            return f"Error: {e}"

    @mcp.tool()
    def wiki_write(
        content: str,
        wiki_dir: str | None = None,
        page: str | None = None,
        rebuild_index: bool = True,
    ) -> str:
        """Create or update a wiki page in pages/.

        See wiki_read('conventions') for page creation rules and frontmatter
        guidance. Pass rebuild_index=false when writing multiple pages, then
        true (or omit) on the last write.

        Args:
            content: Full page content with YAML frontmatter (title, category,
                ingested, updated are required).
            wiki_dir: Wiki directory (default: config value).
            page: Page filename (without .md). If omitted, auto-generated
                from title.
            rebuild_index: Rebuild index.md after writing (default: true).

        Returns confirmation with the page path.
        """
        try:
            from readpile.wiki import WikiStore

            resolved = _resolve_wiki_dir(wiki_dir)
            store = WikiStore(resolved)
            path = store.write_page(page, content, rebuild_index)
            msg = f"Page written: {path}"
            if rebuild_index:
                msg += "\nIndex auto-rebuilt."
            return msg
        except (ValueError, FileNotFoundError) as e:
            return f"Error: {e}"

    @mcp.tool()
    def wiki_list(
        wiki_dir: str | None = None,
        category: str | None = None,
    ) -> str:
        """List all wiki pages with metadata.

        Args:
            wiki_dir: Wiki directory (default: config value).
            category: Filter to a specific category.

        Returns one line per page: name — title [category].
        """
        try:
            from readpile.wiki import WikiStore

            resolved = _resolve_wiki_dir(wiki_dir)
            store = WikiStore(resolved)
            pages = store.list_pages(category)
            if not pages:
                return "No pages found."
            lines = [f"{p['name']} — {p['title']} [{p['category']}]" for p in pages]
            return "\n".join(lines)
        except (ValueError, FileNotFoundError) as e:
            return f"Error: {e}"

    @mcp.tool()
    def wiki_search(
        query: str,
        wiki_dir: str | None = None,
        scope: str = "pages",
    ) -> str:
        """Full-text search across wiki pages and/or sources.

        Args:
            query: Search term (case-insensitive substring match).
            wiki_dir: Wiki directory (default: config value).
            scope: Search scope — "pages" (default), "sources", or "all".

        Returns matching pages with context snippets.
        """
        try:
            from readpile.wiki import WikiStore

            resolved = _resolve_wiki_dir(wiki_dir)
            store = WikiStore(resolved)
            results = store.search(query, scope)
            if not results:
                return "No results found."
            lines = []
            for r in results:
                lines.append(f"### {r['name']} — {r['title']}")
                for m in r["matches"]:
                    lines.append(f"  Line {m['line_number']}:")
                    for ctx_line in m["context"].splitlines():
                        lines.append(f"    {ctx_line}")
                lines.append("")
            return "\n".join(lines)
        except (ValueError, FileNotFoundError) as e:
            return f"Error: {e}"

    @mcp.tool()
    def wiki_log(
        entry: str,
        wiki_dir: str | None = None,
    ) -> str:
        """Append a timestamped entry to the wiki log.

        The tool handles the ## [date] prefix and file append — pass only the
        new entry text (e.g., 'ingest | "Title" | URL\\n- Created page: x.md').

        Args:
            entry: Log entry text (without date prefix).
            wiki_dir: Wiki directory (default: config value).

        Returns confirmation with the appended entry.
        """
        try:
            from readpile.wiki import WikiStore
            from datetime import date

            resolved = _resolve_wiki_dir(wiki_dir)
            store = WikiStore(resolved)
            store.append_log(entry)
            return f"Logged: ## [{date.today().isoformat()}] {entry}"
        except (ValueError, FileNotFoundError) as e:
            return f"Error: {e}"

    @mcp.tool()
    def wiki_delete(
        page: str,
        wiki_dir: str | None = None,
    ) -> str:
        """Delete a wiki page and rebuild the index.

        Args:
            page: Page name to delete (without .md extension).
            wiki_dir: Wiki directory (default: config value).

        Returns confirmation. Follow up with wiki_log to record the deletion.
        """
        try:
            from readpile.wiki import WikiStore

            resolved = _resolve_wiki_dir(wiki_dir)
            store = WikiStore(resolved)
            store.delete_page(page)
            return f"Deleted page: {page}\nIndex auto-rebuilt."
        except FileNotFoundError as e:
            return f"Error: {e}"
        except ValueError as e:
            return f"Error: {e}"

    return mcp


async def _mcp_crawl_blog(url: str, max_pages: int) -> list[str]:
    """Crawl blog posts — Playwright first, HTTP fallback."""
    try:
        return await _mcp_crawl_blog_playwright(url, max_pages)
    except (ImportError, SystemExit, OSError, Exception) as exc:
        if isinstance(exc, (ImportError, SystemExit)):
            pass
        elif "Executable doesn't exist" in str(exc) or "browser" in str(exc).lower():
            pass
        else:
            raise
    return await _mcp_crawl_blog_httpx(url, max_pages)


async def _mcp_crawl_blog_playwright(url: str, max_pages: int) -> list[str]:
    """Crawl blog posts using Playwright directly (no asyncio.run)."""
    from playwright.async_api import async_playwright

    from readpile.core.browser import launch_chromium
    from readpile.crawlers.blog import BlogCrawler

    async with async_playwright() as pw:
        browser = await launch_chromium(pw, headless=True)
        context = await browser.new_context()
        try:
            crawler = BlogCrawler(context, url, max_posts=max_pages)
            return await crawler.crawl()
        finally:
            await context.close()
            await browser.close()


async def _mcp_crawl_blog_httpx(url: str, max_pages: int) -> list[str]:
    """Fallback: discover blog post URLs using httpx + BeautifulSoup."""
    import httpx
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin, urldefrag, urlparse

    from readpile.crawlers.blog import BlogPostDetector

    detector = BlogPostDetector()
    parsed_base = urlparse(url)
    base_domain = parsed_base.netloc.lower().removeprefix("www.")

    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        # Try sitemap.xml first
        sitemap_url = f"{parsed_base.scheme}://{parsed_base.netloc}/sitemap.xml"
        sitemap_urls = await _try_sitemap(client, sitemap_url)
        if sitemap_urls:
            candidates = [
                u for u in sitemap_urls
                if detector.detect_url_only(u) > -0.3
            ]
            return sorted(candidates)[:max_pages]

        # Fall back to link extraction from the page
        resp = await client.get(url, headers={"User-Agent": "readpile/0.1"})
        resp.raise_for_status()
        html = resp.text

    soup = BeautifulSoup(html, "lxml")
    candidates: list[str] = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        absolute = urljoin(url, href)
        defragged, _ = urldefrag(absolute)
        link_parsed = urlparse(defragged)
        link_domain = link_parsed.netloc.lower().removeprefix("www.")
        if link_domain != base_domain:
            continue
        if detector.detect_url_only(defragged) > -0.3:
            candidates.append(defragged)

    return sorted(set(candidates))[:max_pages]


async def _mcp_crawl_site(url: str, max_pages: int) -> list[str]:
    """Crawl site URLs — Playwright first, HTTP fallback."""
    try:
        return await _mcp_crawl_site_playwright(url, max_pages)
    except (ImportError, SystemExit, OSError, Exception) as exc:
        if isinstance(exc, (ImportError, SystemExit)):
            pass
        elif "Executable doesn't exist" in str(exc) or "browser" in str(exc).lower():
            pass
        else:
            raise
    return await _mcp_crawl_site_httpx(url, max_pages)


async def _mcp_crawl_site_playwright(url: str, max_pages: int) -> list[str]:
    """Crawl site URLs using SiteCrawler directly (no asyncio.run)."""
    from readpile.crawlers.site import SiteCrawler

    crawler = SiteCrawler(url, max_depth=10, scope="prefix", max_pages=max_pages)
    return await crawler.crawl()


async def _mcp_crawl_site_httpx(url: str, max_pages: int) -> list[str]:
    """Fallback: discover site URLs using httpx + BeautifulSoup (BFS, no JS)."""
    import httpx
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin, urldefrag, urlparse

    parsed_base = urlparse(url)
    site_prefix = f"{parsed_base.scheme}://{parsed_base.netloc}{parsed_base.path}".rstrip("/")

    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        # Try sitemap.xml first
        sitemap_url = f"{parsed_base.scheme}://{parsed_base.netloc}/sitemap.xml"
        sitemap_urls = await _try_sitemap(client, sitemap_url)
        if sitemap_urls:
            filtered = [u for u in sitemap_urls if u.startswith(site_prefix)]
            return sorted(filtered)[:max_pages]

        # BFS with httpx
        visited: set[str] = set()
        queue = [url]

        while queue and len(visited) < max_pages:
            current = queue.pop(0)
            clean = current.split("#")[0].split("?")[0].rstrip("/")
            if clean in visited:
                continue
            visited.add(clean)

            try:
                resp = await client.get(current, headers={"User-Agent": "readpile/0.1"})
                if resp.status_code >= 400:
                    continue
                html = resp.text
            except httpx.HTTPError:
                continue

            soup = BeautifulSoup(html, "lxml")
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if not href or href.startswith(("#", "javascript:", "mailto:")):
                    continue
                absolute = urljoin(current, href)
                defragged, _ = urldefrag(absolute)
                clean_link = defragged.split("?")[0].rstrip("/")
                if clean_link.startswith(site_prefix) and clean_link not in visited:
                    queue.append(defragged)

    return sorted(visited)


async def _try_sitemap(client, sitemap_url: str) -> list[str]:
    """Try to parse a sitemap.xml and return URLs, or empty list on failure."""
    try:
        from bs4 import BeautifulSoup

        resp = await client.get(sitemap_url, headers={"User-Agent": "readpile/0.1"})
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "lxml-xml")
        urls = [loc.text.strip() for loc in soup.find_all("loc") if loc.text]
        return urls
    except Exception:
        return []


from readpile.crawlers.discovery import (
    resolve_youtube_feed as _resolve_youtube_channel_feed,
    discover_feed as _discover_feed,
    discover_podcast_feed as _discover_podcast_feed,
)


async def _extract_media_url(url: str) -> str | None:
    """Fetch a webpage and extract the first embedded YouTube or audio URL."""
    import re
    import httpx
    from bs4 import BeautifulSoup

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            resp = await client.get(url, headers={"User-Agent": "readpile/0.1"})
            resp.raise_for_status()
            html = resp.text
    except Exception:
        return None

    soup = BeautifulSoup(html, "lxml")

    # 1. YouTube embeds: <iframe src="youtube.com/embed/VIDEO_ID">
    for iframe in soup.find_all("iframe", src=True):
        src = iframe["src"]
        match = re.search(r"youtube\.com/embed/([A-Za-z0-9_-]{11})", src)
        if match:
            return f"https://www.youtube.com/watch?v={match.group(1)}"
        if "youtube.com" in src or "youtu.be" in src:
            return src

    # 2. YouTube links in the page
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r"(youtube\.com/watch|youtu\.be/)", href):
            return href

    # 3. <audio> elements with src
    for audio in soup.find_all("audio", src=True):
        return audio["src"]
    for source in soup.find_all("source", src=True):
        src = source["src"]
        if any(src.lower().endswith(ext) for ext in (".mp3", ".m4a", ".wav", ".ogg", ".aac")):
            return src

    # 4. Direct audio links
    audio_exts = (".mp3", ".m4a", ".wav", ".ogg", ".aac")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if any(href.lower().endswith(ext) for ext in audio_exts):
            return href

    # 5. YouTube URLs in raw HTML (e.g., in JSON-LD, data attributes, JS)
    yt_match = re.search(
        r"https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})",
        html,
    )
    if yt_match:
        return f"https://www.youtube.com/watch?v={yt_match.group(1)}"

    return None


async def _transcribe_via_fallback(fallback_url: str, language: str) -> str | None:
    """Try to transcribe by finding an embedded YouTube video at fallback_url.

    Returns the transcript string on success, or None if no YouTube embed found.
    """
    from readpile.core.detector import detect_url_type, URLType

    media_url = await _extract_media_url(fallback_url)
    if not media_url:
        return None

    media_type = detect_url_type(media_url)
    if media_type == URLType.youtube:
        from readpile.transcribers.youtube import transcribe_youtube
        item = transcribe_youtube(media_url, language)
        return item.to_stdout()

    return None


mcp = _create_server()


def main():
    mcp.run()
