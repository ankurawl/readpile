# mediakit

Content extraction toolkit for LLMs. Scrape articles, transcribe videos, crawl feeds, and archive content.

## MCP Server

mediakit exposes 5 tools via MCP (Model Context Protocol):

- **scrape** — Extract article/webpage content from a URL (YAML front matter + markdown)
- **transcribe** — Transcribe YouTube videos or audio/video URLs
- **crawl** — Discover content URLs from RSS feeds, blogs, or sites
- **archive** — Save content to disk as markdown files
- **detect_type** — Identify URL type (youtube, rss, blog, audio, video, etc.)

### Setup

The `.mcp.json` at repo root auto-configures Claude Code. For other clients:

```json
{
  "mcpServers": {
    "mediakit": {
      "command": "mediakit-mcp",
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
mediakit init              # Generate config file
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
src/mediakit/
├── cli/           # Typer CLI commands
├── scrapers/      # Article + webpage extraction
├── transcribers/  # YouTube + audio transcription
├── crawlers/      # RSS, blog, site crawlers
├── core/          # Config, models, archiver, detector
├── bot/           # Telegram bot
└── mcp_server.py  # MCP server (FastMCP)
```
