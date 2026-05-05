"""MCP server — expose mediakit tools via Model Context Protocol."""

from __future__ import annotations


def _create_server():
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("mediakit")

    @mcp.tool()
    async def scrape(url: str) -> str:
        """Scrape a URL and return its content as YAML front matter + markdown.

        Tries structured article extraction first, falls back to generic
        webpage scraping if the article is too short or missing.
        """
        try:
            from mediakit.scrapers import scrape_url
            item = await scrape_url(url)
            return item.to_stdout()
        except SystemExit as e:
            return str(e)

    @mcp.tool()
    def transcribe(source: str, language: str = "en") -> str:
        """Transcribe audio/video content from a URL.

        Supports YouTube URLs and direct audio/video URLs.
        Returns YAML front matter + markdown transcript.
        """
        try:
            from mediakit.core.detector import detect_url_type, URLType

            url_type = detect_url_type(source)

            if url_type == URLType.youtube:
                from mediakit.transcribers.youtube import transcribe_youtube
                item = transcribe_youtube(source, language)
                return item.to_stdout()

            if url_type in (URLType.audio_file, URLType.video):
                if "://" not in source:
                    return "Error: local file paths are not supported. Provide a URL."
                from mediakit.transcribers.audio import transcribe_from_url
                item = transcribe_from_url(source)
                return item.to_stdout()

            return (
                f"Error: URL type '{url_type.value}' is not transcribable. "
                "Supported types: youtube, audio_file, video."
            )
        except SystemExit as e:
            return str(e)

    @mcp.tool()
    def crawl(
        url: str,
        mode: str = "auto",
        recent: int | None = None,
        limit: int | None = None,
    ) -> list[str]:
        """Discover content URLs from a website, blog, or RSS feed.

        Args:
            url: URL to crawl.
            mode: Crawl mode — "auto", "rss", "blog", or "site".
            recent: Only return N most recent items (RSS mode only).
            limit: Max pages/posts to discover (blog/site modes).

        Returns a list of discovered URLs.
        """
        try:
            from mediakit.cli.crawl import _crawl_rss, _crawl_blog, _crawl_site, _detect_crawl_mode

            effective_mode = mode
            if effective_mode == "auto":
                effective_mode = _detect_crawl_mode(url)

            if effective_mode == "rss":
                return _crawl_rss(url, recent)
            elif effective_mode == "blog":
                return _crawl_blog(url, max_depth=10, max_pages=limit or 100, login=False)
            elif effective_mode == "site":
                return _crawl_site(url, max_depth=10, max_pages=limit or 100, scope="prefix")
            else:
                return [f"Error: Unknown mode '{effective_mode}'. Use: auto, rss, blog, site."]
        except SystemExit as e:
            return [str(e)]

    @mcp.tool()
    def archive(
        content: str,
        title: str,
        source_url: str,
        content_type: str = "article",
        dir: str | None = None,
    ) -> str:
        """Save content to disk as a markdown file with YAML front matter.

        Args:
            content: The text content to archive.
            title: Title for the content.
            source_url: Original source URL.
            content_type: One of: article, youtube, audio, podcast, webpage.
            dir: Output directory (default: ~/mediakit-output or config value).

        Returns the path to the saved file.
        """
        try:
            from pathlib import Path
            from mediakit.core.models import ContentItem, ContentType
            from mediakit.core.archiver import Archiver
            from mediakit.core.config import load_config

            try:
                ct = ContentType(content_type)
            except ValueError:
                valid = ", ".join(t.value for t in ContentType)
                return f"Error: invalid content_type '{content_type}'. Valid options: {valid}"

            item = ContentItem(
                text=content,
                title=title,
                source_url=source_url,
                content_type=ct,
            )

            if dir is not None:
                output_dir = Path(dir).expanduser()
            else:
                config = load_config()
                output_dir = Path(
                    config.get("general", {}).get("output_dir", "~/mediakit-output")
                ).expanduser()

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
            from mediakit.core.detector import detect_url_type
            return detect_url_type(url).value
        except SystemExit as e:
            return str(e)

    return mcp


mcp = _create_server()


def main():
    mcp.run()
