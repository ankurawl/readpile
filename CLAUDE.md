# readpile

Content extraction toolkit for LLMs. Build a personal knowledge base from articles, videos, podcasts, and documentation. See [README.md](README.md) for user-facing docs and [CONTRIBUTING.md](CONTRIBUTING.md) for development setup.

## Terminology

- **Source file** — raw extracted content in `~/my-wiki/sources/` (immutable)
- **Wiki page** — LLM-synthesized page in `~/my-wiki/pages/`
- **Feed** — RSS feed, YouTube channel, or podcast subscription in `~/.readpile/feeds.toml`

## MCP Server

readpile exposes 13 tools via MCP (Model Context Protocol):

- **scrape** — Extract article/webpage content from a URL (YAML front matter + markdown)
- **transcribe** — Transcribe YouTube videos, audio/video URLs, or webpages with embedded YouTube players
- **crawl** — Discover content URLs from RSS feeds, blogs, sites, or podcasts. Auto-discovers RSS feeds from non-feed URLs (e.g., `crawl("blog.com", mode="rss")` finds the feed automatically)
- **batch_scrape** — Scrape multiple URLs in one call with concurrency control
- **detect_type** — Identify URL type (youtube, rss, blog, audio, video, etc.)
- **wiki_init** — Create a wiki with directory structure, `.wiki.toml` config, and `wiki-conventions.md`
- **wiki_save_source** — Save raw content to the wiki's `sources/` directory as a source file
- **wiki_read** — Read a wiki page, source file, or special file (index, log, conventions)
- **wiki_write** — Create or update a wiki page in `pages/` with frontmatter validation
- **wiki_list** — List all wiki pages with metadata, optionally filtered by category
- **wiki_search** — Full-text search across pages and/or source files
- **wiki_log** — Append a timestamped entry to the wiki's operation log
- **wiki_delete** — Delete a wiki page and rebuild the index

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
wiki_save_source(content, title, ...)  → Save to wiki sources (one call per item)
```

**Podcast discovery and summarization:**
```
crawl(url, mode="podcast", recent=15)  → JSON metadata with episode titles, dates, descriptions, audio URLs
transcribe(episode_url)                → Full transcript via embedded YouTube (many podcasts embed YT players)
transcribe(audio_url,                  → If audio fails (no ffmpeg), fallback_url checks the episode
  fallback_url=episode_url)              webpage for an embedded YouTube video and transcribes that instead
wiki_save_source(content, title, ...)  → Save to wiki sources (one call per item)
```

**Blog bulk-read:**
```
crawl(url, mode="rss", metadata=True)  → JSON metadata for all entries (auto-discovers feed if needed)
batch_scrape(selected_urls)            → Full content of multiple articles in one call
wiki_save_source(content, title, ...)  → Save each article to wiki sources
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
content URL                # Auto-detect and extract
readpile init              # Generate config + create wiki
readpile wiki init PATH    # Create an additional wiki
readpile wiki list         # List wiki pages
readpile wiki search QUERY # Search wiki pages
readpile wiki log          # View wiki log
readpile sync              # Check email + subscriptions, send digest
readpile synthesize        # Synthesize source files into wiki pages
readpile feeds add URL   # Add a feed subscription (updates existing if URL matches)
readpile feeds list      # List feed subscriptions with serial numbers
readpile feeds remove ID   # Remove feed(s) by index (1, 3-5) or name
readpile status            # Show sync overview
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
├── cli/           # Typer CLI commands (main.py is the entry point)
├── scrapers/      # Article + webpage extraction
├── transcribers/  # YouTube + audio transcription
├── crawlers/      # RSS, blog, site crawlers + feed/podcast/YouTube discovery
├── core/          # Config, models, archiver, detector
├── sync/          # Sync pipeline (email, feeds, digest, synthesis)
├── wiki/          # LLMWiki module (models, store)
└── mcp_server.py  # MCP server (FastMCP)
```

## LLMWiki

An LLM-maintained wiki layer on top of readpile's content extraction. Inspired by Karpathy's LLMWiki concept — instead of re-deriving answers from raw documents, the LLM incrementally builds a structured wiki that compounds knowledge over time.

### Wiki directory structure

```
~/my-wiki/
├── .wiki.toml              # schema: wiki name, categories
├── wiki-conventions.md     # behavioral playbook for the LLM
├── index.md                # auto-generated catalog (never edit manually)
├── log.md                  # append-only timeline of operations
├── sources/                # source files — raw content (immutable, saved via wiki_save_source)
└── pages/                  # wiki pages (LLM-created via wiki_write)
```

### Wiki page frontmatter (three timestamps)

```yaml
title: "Page Title"
category: concept           # must be in .wiki.toml categories
tags: [tag1, tag2]
sources: [sources/2026-05-10_article.md]
related: [other-page]
source_date: 2026-05-08     # when the original content was published
ingested: 2026-05-10        # when added to wiki (never changes)
updated: 2026-05-17         # when wiki page was last modified
```

### Ingest workflow (LLM-orchestrated via conventions file)

```
scrape(url)                                → raw content
wiki_save_source(content, title, ...)      → saves to sources/
wiki_read("index")                         → current wiki state
wiki_write(content, rebuild_index=false)   → intermediate pages
wiki_write(content)                        → final page (rebuilds index)
wiki_log("ingest | Title | URL\n...")      → append-only log entry
```

### Key design decisions

- **Thin tools + conventions file**: Tools do file I/O; behavioral rules live in `wiki-conventions.md` (editable markdown, not Python code)
- **Auto-managed index**: `wiki_write` and `wiki_delete` rebuild `index.md` automatically. Pass `rebuild_index=false` for batch writes, `true` on the last one
- **Append-only log**: `wiki_log` handles date prefix and file append — avoids fragile read-rewrite pattern
- **`exploration` category**: Query-derived pages use `exploration` to distinguish from source-derived summaries/comparisons
- **Obsidian compatible**: `[[wikilinks]]`, YAML frontmatter, directory structure all work natively in Obsidian

### Config

```toml
[wiki]
default_dir = "~/my-wiki"   # in ~/.readpile/config.toml
```

## Sync Pipeline

Automated content collection and knowledge synthesis via email and feed subscriptions (RSS feeds, YouTube channels, podcasts).

### Commands

```
readpile sync              # Check email + subscriptions, send daily digest
readpile sync --no-email   # Subscriptions only
readpile sync --no-feeds   # Email only
readpile sync --dry-run    # Preview without saving
readpile sync --reset-feeds # Clear feed state, re-process
readpile synthesize --pending  # Synthesize approved items (cron)
readpile synthesize --all     # Synthesize everything
readpile synthesize --source PATH  # Specific source file
readpile feeds add URL      # Add feed subscription (auto-detect)
readpile feeds list         # List all feed subscriptions
readpile feeds remove NAME  # Remove a feed subscription
readpile feeds enable NAME  # Re-enable disabled feed subscription
readpile status               # Show sync overview
```

### Architecture

Sync reuses existing extraction/transcription code — no logic is duplicated:
- `scrape_url()`, `scrape_article()` for articles
- `transcribe_youtube()` for video
- `crawl_rss_detailed()` for feed discovery
- `WikiStore.save_source_from_item()` for wiki storage

The sync module (`src/readpile/sync/`) contains:
- `pipeline.py` — async orchestrator (email → feeds → save → digest)
- `synthesizer.py` — LLM wiki page creation with quality gate
- `state.py` — JSON-backed state tracking + lock file
- `sources.py` — feed registry (reads/writes feeds.toml)
- `feeds.py` — feed crawling with rate limiting
- `digest.py` — topic grouping (LLM) + email sending
- `reply.py` — parse user replies to digest emails
- `llm.py` — LLM calls via OpenAI-compatible API
- `urls.py` — URL normalization for dedup
- `email/` — Gmail OAuth provider + content extraction

### Config

```toml
[llm]
base_url = "anthropic"
model = "claude-sonnet-4-6"
api_key = "..."

[sync]
synthesis_wait_days = 7
max_auto_synthesize_per_run = 20

[sync.email]
enabled = true
provider = "gmail"
account = "readpile-inbox@gmail.com"

[sync.digest]
enabled = true
to = "personal@email.com"
smtp_password = "..."
```

Feed subscriptions are stored separately in `~/.readpile/feeds.toml` (machine-managed via `readpile feeds` commands).

### Security

- All secrets stored in `~/.readpile/config.toml` (chmod 600). OAuth credentials in `~/.readpile/` (chmod 600).

