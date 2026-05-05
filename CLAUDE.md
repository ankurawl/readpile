# readpile

Content extraction toolkit for LLMs. Build a personal library from articles, videos, podcasts, and documentation.

## MCP Server

readpile exposes 5 tools via MCP (Model Context Protocol):

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
