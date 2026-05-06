# readpile

Content extraction toolkit for LLMs. Build a personal library from articles, videos, podcasts, and documentation.

## MCP Server

readpile exposes 6 tools via MCP (Model Context Protocol):

- **scrape** — Extract article/webpage content from a URL (YAML front matter + markdown)
- **transcribe** — Transcribe YouTube videos, audio/video URLs, or webpages with embedded YouTube players
- **crawl** — Discover content URLs from RSS feeds, blogs, sites, or podcasts. Auto-discovers RSS feeds from non-feed URLs (e.g., `crawl("blog.com", mode="rss")` finds the feed automatically)
- **batch_scrape** — Scrape multiple URLs in one call with concurrency control. Use `archive_dir` to save all results to disk in one step
- **archive** — Save content to disk as markdown files
- **detect_type** — Identify URL type (youtube, rss, blog, audio, video, etc.)

### crawl tool details

Modes: `auto`, `rss`, `blog`, `site`, `podcast`, `youtube`

- `metadata=True` (RSS/podcast/youtube modes): Returns JSON metadata per entry (title, date, author, description, audio_url, duration) instead of bare URLs
- `mode="podcast"`: Auto-discovers the podcast RSS feed from any URL, filters to audio-only entries, always returns metadata
- `mode="youtube"`: Resolves YouTube channel URLs (@handle, /channel/ID) to their RSS feed, returns up to 15 most recent videos
- `mode="rss"`: Parses RSS/Atom feeds. Auto-discovers feeds from non-feed URLs (checks `<link rel="alternate">` tags, then tries `/feed`, `/feed.xml`, `/rss`)
- `mode="blog"`: Discovers blog post URLs via Playwright or HTTP fallback. Returns URLs in alphabetical order (not chronological). For date-sorted results, use `mode="rss"` instead
- `recent=N`: Limit to N most recent entries (RSS/podcast/youtube modes)

### YouTube IP blocks

YouTube may block transcript requests from certain IPs (cloud, corporate, VPN). When this happens,
readpile automatically falls back to yt-dlp with cookie authentication. If that also fails,
the error message tells the user how to export browser cookies. The cookie file is checked at:
1. `~/.readpile/youtube-cookies.txt`
2. `YOUTUBE_COOKIES` env var
3. `youtube_cookies` in `~/.readpile/config.toml`

If a user reports YouTube transcription failing, suggest they export cookies:
```
yt-dlp --cookies-from-browser chrome --cookies ~/.readpile/youtube-cookies.txt https://youtube.com
```

### Workflows

**YouTube channel transcription:**
```
crawl(url, mode="youtube", recent=5)   → Video URLs/metadata from a YouTube channel (@handle)
transcribe(video_url)                  → Full transcript using YouTube captions (no ffmpeg needed)
archive(content, title, source_url)    → Save to disk (one call per item)
```

**Podcast discovery and summarization:**
```
crawl(url, mode="podcast", recent=15)  → JSON metadata with episode titles, dates, descriptions, audio URLs
transcribe(episode_url)                → Full transcript via embedded YouTube (many podcasts embed YT players)
transcribe(audio_url,                  → If audio fails (no ffmpeg), fallback_url checks the episode
  fallback_url=episode_url)              webpage for an embedded YouTube video and transcribes that instead
archive(content, title, source_url)    → Save to disk (one call per item)
```

**Blog bulk-read:**
```
crawl(url, mode="rss", metadata=True)  → JSON metadata for all entries (auto-discovers feed if needed)
batch_scrape(selected_urls,            → Full content of multiple articles in one call
  archive_dir="/path/to/library")        + automatically saved to disk
archive(content, title, source_url)    → Or save to disk individually (one call per item)
```

### Setup

The `.mcp.json` at repo root auto-configures Claude Code. For other clients:

```json
{
  "mcpServers": {
    "readpile": {
      "command": "readpile-mcp",
      "args": [],
      "type": "stdio"
    }
  }
}
```

## CLI Tools

```
scrape URL                 # Extract article/webpage content
transcribe URL             # Transcribe YouTube/audio/video
crawl URL                  # Discover content URLs
archive < content.md       # Save to disk
content URL                # Auto-detect and extract
content URL --archive      # Extract + save to disk
readpile init              # Generate config file
content-bot start          # Start Telegram bot
```

## ContentItem Format

All tools output YAML front matter + markdown body:

```markdown
---
title: "Article Title"
source_url: https://example.com/post
content_type: article
---

Markdown content here...
```

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Project Structure

```
src/readpile/
├── cli/           # Typer CLI commands
├── scrapers/      # Article + webpage extraction
├── transcribers/  # YouTube + audio transcription
├── crawlers/      # RSS, blog, site crawlers
├── core/          # Config, models, archiver, detector
├── bot/           # Telegram bot
└── mcp_server.py  # MCP server (FastMCP)
```
