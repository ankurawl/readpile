# readpile

Content extraction toolkit for LLMs. Build a personal library from articles, videos, podcasts, and documentation.

## MCP Server

readpile exposes 6 tools via MCP (Model Context Protocol):

- **scrape** — Extract article/webpage content from a URL (YAML front matter + markdown)
- **transcribe** — Transcribe YouTube videos or audio/video URLs
- **crawl** — Discover content URLs from RSS feeds, blogs, sites, or podcasts
- **batch_scrape** — Scrape multiple URLs in one call with concurrency control
- **archive** — Save content to disk as markdown files
- **detect_type** — Identify URL type (youtube, rss, blog, audio, video, etc.)

### crawl tool details

Modes: `auto`, `rss`, `blog`, `site`, `podcast`, `youtube`

- `metadata=True` (RSS/podcast/youtube modes): Returns JSON metadata per entry (title, date, author, description, audio_url, duration) instead of bare URLs
- `mode="podcast"`: Auto-discovers the podcast RSS feed from any URL, filters to audio-only entries, always returns metadata
- `mode="youtube"`: Resolves YouTube channel URLs (@handle, /channel/ID) to their RSS feed, returns up to 15 most recent videos
- `recent=N`: Limit to N most recent entries (RSS/podcast/youtube modes)

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
transcribe(audio_url)                  → Full transcript of a specific episode
archive(content, title, source_url)    → Save to disk (one call per item)
```

**Blog bulk-read:**
```
crawl(url, mode="rss", metadata=True)  → JSON metadata for all entries
batch_scrape(selected_urls)            → Full content of multiple articles in one call
archive(content, title, source_url)    → Save to disk (one call per item)
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
