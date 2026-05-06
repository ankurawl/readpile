# readpile

**Your personal library for the modern web.** Collect articles, transcribe videos, crawl entire blogs — then search, shortlist, and revisit anything on your own terms. Use it from the command line, or let your LLM curate your library directly via MCP.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)]()
[![Tests](https://img.shields.io/badge/tests-225%20passing-brightgreen.svg)]()

---

## What is readpile?

The best content on the web is scattered across blogs, YouTube channels, podcasts, and documentation sites. readpile brings it all into one place — your personal library. Collect anything worth keeping, search across everything you've saved, and come back to it whenever you're ready.

**The problem it solves:** You follow dozens of sources — conference talks, newsletters, technical blogs, podcast episodes, reference docs. Keeping up means clicking through pages, waiting for videos, copying text, and losing track of what you've already consumed. readpile handles the collecting so you can focus on the reading — catch up when you have time, skim what matters, save the rest for later.

### What you can do with it

- **Build your library** — Collect articles, transcripts, and documentation into a personal archive you own. Search across everything, revisit old reads, and keep a growing reference collection that's always available.
- **Catch up on your terms** — Pull the last 10 posts from a blog, 5 episodes from a podcast, or a full YouTube playlist. Skim now, read deeply later, or save as reference material — your schedule, your pace.
- **Create custom digests** — Combine content from multiple sources into a single briefing. Shortlist the pieces that matter, summarize the rest, and start your day already caught up.
- **Give your LLM eyes and ears** — Connect readpile as an MCP server and your AI assistant can read any webpage, watch any YouTube video, or crawl any site — then help you search, compare, and make sense of it all.
- **Research at scale** — Crawl an entire documentation site or blog archive. Search across hundreds of pages locally, pull out what's relevant, and build a focused reference collection for any project.

### What it can extract

| Source | What you get |
|--------|-------------|
| **Blog posts & articles** | Clean Markdown with title, author, date, tags — extracted from the rendered page |
| **YouTube videos** | Full transcript with timestamps, via YouTube's caption API (instant, free) |
| **YouTube channels** | Discover recent videos from any channel (`@handle`, `/channel/ID`) via RSS |
| **Podcasts** | Auto-discover podcast RSS feeds, get episode metadata, transcribe episodes |
| **Audio & video files** | Whisper-powered transcription with optional speaker diarization |
| **RSS/Atom feeds** | All entry URLs with optional metadata (title, date, description, audio URLs) |
| **Documentation sites** | Recursive crawl that discovers every page under a URL prefix |
| **Any webpage** | Headless Chromium rendering + intelligent content extraction (HTTP fallback when Chromium unavailable) |

### How it fits together

```
                          ┌─────────┐
                     ┌───→│ scrape  │───→ article text
                     │    └─────────┘
  ┌───────┐    ┌─────┴──┐ ┌───────────┐
  │ crawl │───→│  URLs  │→│transcribe │───→ transcript
  └───────┘    └─────┬──┘ └───────────┘
                     │    ┌─────────┐        ┌─────────┐
                     └───→│ content │───────→│ archive │───→ Markdown files
                          └─────────┘        └─────────┘
                          (auto-detect)
```

Every piece of content becomes a **ContentItem** — a Markdown document with YAML front matter — that pipes cleanly between commands, works with any Markdown viewer, and is easy for LLMs to parse. Think of each one as a book on your shelf:

```markdown
---
title: "How to Build CLI Tools"
source_url: https://example.com/post
content_type: article
date: 2026-04-25
author: "Jane Doe"
word_count: 2400
---

The full article text in clean Markdown...
```

---

## Quick Start

### Install

```bash
pip install readpile
python -m playwright install chromium    # needed for web scraping
```

### Use from the command line

```bash
# Extract content from any URL (auto-detects type)
content https://youtube.com/watch?v=dQw4w9WgXcQ
content https://example.com/blog/post

# Scrape a single article
scrape https://example.com/blog/great-post

# Transcribe a YouTube video
transcribe https://youtube.com/watch?v=dQw4w9WgXcQ

# Crawl a blog and archive every post
crawl https://example.com/blog | scrape --batch | archive --dir ./blog-archive/

# Extract and save to disk
content https://example.com/post --archive
```

### Use from an LLM (via MCP)

readpile ships as an [MCP server](https://modelcontextprotocol.io/) that any compatible LLM client can discover and use. Once connected, your LLM becomes a librarian — it can collect pages, transcribe videos, crawl sites, and archive content into your library, then help you read, compare, or make sense of what you've gathered.

**Claude Code** — auto-configured via `.mcp.json` at the repo root:

```bash
pip install readpile[mcp]
python -m playwright install chromium
# Claude Code discovers the server automatically
```

**Other MCP clients** — add to your client's MCP configuration:

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

Available MCP tools:

| MCP Tool | What it does |
|----------|-------------|
| `scrape(url)` | Extract article/webpage content as Markdown |
| `transcribe(source, language, fallback_url)` | Transcribe YouTube, audio/video URLs, or webpages with embedded YouTube. Use `fallback_url` for podcast episodes where audio needs ffmpeg but the webpage has a YouTube embed |
| `crawl(url, mode, recent, limit, metadata)` | Discover content URLs from feeds, blogs, sites, YouTube channels, or podcasts |
| `batch_scrape(urls, concurrency)` | Scrape multiple URLs in one call with concurrency control |
| `archive(content, title, source_url, date, author, dir)` | Save content to disk as a Markdown file |
| `detect_type(url)` | Identify URL type (youtube, youtube_channel, rss, blog, audio, etc.) |

The `crawl` tool supports these modes:

| Mode | What it does |
|------|-------------|
| `auto` | Auto-detect the best mode from the URL |
| `rss` | Parse RSS/Atom feeds. Use `metadata=True` to get JSON with titles, dates, descriptions |
| `podcast` | Auto-discover podcast RSS feed from any URL, filter to audio-only episodes |
| `youtube` | Resolve YouTube channel URLs to their RSS feed, return recent videos |
| `blog` | Discover blog post URLs via Playwright or HTTP fallback |
| `site` | Recursive site crawl under a URL prefix |

---

## Example Workflows

### Morning briefing from multiple sources

```bash
# Collect today's reading from 3 blogs + a podcast into one folder
{
  crawl https://blog-a.com/feed.xml --recent 3 | scrape --batch
  crawl https://blog-b.com/blog | scrape --batch
  transcribe https://youtube.com/watch?v=latest-talk
} | archive --batch --dir ./daily-briefing/
# Then ask your LLM: "Summarize today's briefing into 5 bullet points"
```

### Save a blog before it disappears

```bash
crawl https://closing-soon.com/blog | scrape --batch | archive --dir ./saved-blog/
# Every post preserved as YYYY-MM-DD_title-slug.md with full metadata
```

### Build a research library

```bash
# Crawl docs, grab relevant videos, pull it all into one folder
crawl https://docs.example.com --mode site --depth 3 | scrape --batch | archive --dir ./research/
transcribe https://youtube.com/watch?v=related-talk | archive --dir ./research/
# Your research library — instantly searchable, LLM-ready
```

### Catch up on a podcast

```bash
crawl https://podcast.com/feed.xml --recent 5
# Returns 5 episode URLs — pipe to transcribe, then read at your own pace
```

### Catch up on a YouTube channel

Using MCP, your LLM can discover and transcribe recent videos from any YouTube channel:

```
crawl("youtube.com/@channelname", recent=5)  → 5 most recent video URLs
transcribe(video_url)                        → full transcript via YouTube captions
archive(content, title, source_url)          → save to your library
```

### Discover and summarize a podcast

Using MCP, your LLM can find podcast episodes and get structured metadata in one call:

```
crawl("newsletter.com/podcast", mode="podcast", recent=10)
  → auto-discovers RSS feed, filters to audio episodes
  → returns JSON with title, date, description, audio URL, duration per episode

transcribe(episode_url)
  → if episode page has an embedded YouTube player, transcribes via captions (no ffmpeg needed)

transcribe(audio_url, fallback_url=episode_url)
  → tries audio transcription first; if ffmpeg is missing, checks the episode
    webpage for an embedded YouTube video and transcribes that instead
```

### Collect from behind a login wall

```bash
crawl https://members.example.com/blog --login | scrape --batch | archive --dir ./members/
# Opens a real browser for you to log in, then collects with your session
```

---

## CLI Reference

### `content` — Auto-detect and extract (the all-in-one command)

```bash
content URL                          # extract to stdout
content URL --archive                # extract + save to disk
content URL --no-archive             # force stdout-only
content --batch < urls.txt           # process multiple URLs
```

| Flag | Default | Description |
|------|---------|-------------|
| `--archive / --no-archive` | from config | Force archiving on or off |
| `--dir` | `~/readpile-output` | Output directory when archiving |
| `--batch` | off | Read URLs from stdin (one per line) |

### `scrape` — Extract articles from web pages

Uses a headless Chromium browser. Tries structured article extraction first (readability heuristics), falls back to generic webpage scraping.

```bash
scrape https://example.com/post
crawl https://example.com/blog | scrape --batch
scrape URL --no-headless --no-robots     # visible browser, skip robots.txt
```

### `transcribe` — Transcribe audio and video

YouTube videos use the captions API (instant). Local and remote audio/video files use OpenAI Whisper.

```bash
transcribe https://youtube.com/watch?v=dQw4w9WgXcQ
transcribe recording.mp3 --model small
transcribe interview.wav --language es --diarize
```

### `crawl` — Discover content URLs

Finds URLs from RSS/Atom feeds, blogs (via Playwright), YouTube channels, or full site crawls. Outputs one URL per line.

```bash
crawl https://example.com/blog                       # auto-detect mode
crawl https://example.com/feed.xml --recent 5        # RSS, 5 most recent
crawl https://docs.example.com --mode site --depth 3 # recursive site crawl
crawl https://members.example.com --mode blog --login # auth via persistent browser
```

Modes: `auto`, `rss`, `blog`, `site`, `podcast`, `youtube`. The `podcast` and `youtube` modes are most powerful via MCP, where they auto-discover feeds and return structured metadata.

### `archive` — Save to disk

Reads ContentItems from stdin and writes Markdown files with standardized naming (`YYYY-MM-DD_title-slug.md`).

```bash
scrape https://example.com/post | archive --dir ./saved/
crawl URL | scrape --batch | archive --batch --dir ./blog/
```

### `readpile init` — Set up configuration

```bash
readpile init
# Prompts: archive by default? output directory?
# Writes ~/.readpile/config.toml
```

### `content-bot` — Telegram bot

```bash
content-bot start     # start the bot
content-bot status    # check if configured
```

---

## Archiving

By default, content goes to stdout. To add content to your library on disk, use `--archive` or set `auto_archive = true` in config.

| Command | `auto_archive = false` (default) | `auto_archive = true` |
|---------|----------------------------------|----------------------|
| `content URL` | stdout only | stdout + save to file |
| `content URL --archive` | stdout + save | stdout + save |
| `content URL --no-archive` | stdout only | stdout only |
| MCP `archive()` | always saves (explicit call) | always saves |

---

## Telegram Bot

An optional Telegram bot — send it any URL and it adds the content to your library. You get back a formatted message plus a downloadable Markdown document.

```bash
pip install readpile[bot]
export TELEGRAM_BOT_TOKEN="your-bot-token"
export ADMIN_CHAT_ID="your-telegram-chat-id"
content-bot start
```

Supports `/set_language`, `/set_style brief|detailed`, `/history`, and admin whitelist commands.

---

## Configuration

```bash
readpile init    # interactive setup, writes ~/.readpile/config.toml
```

```toml
[general]
output_dir = "~/readpile-output"      # where archived files go
auto_archive = false                  # archive by default? (overridden by --archive/--no-archive)
date_format = "YYYY-MM-DD"
filename_max_length = 80

[transcribe]
engine = "auto"                       # "auto" | "whisper" | "whisperx"
whisper_model = "base"                # "tiny" | "base" | "small" | "medium" | "large"
diarize = false                       # speaker diarization (requires HF_TOKEN)

[scrape]
headless = true
respect_robots = true
rate_limit = 1.0                      # seconds between requests

[crawl]
max_depth = 10
max_pages = 100
```

| Environment Variable | Description |
|---------------------|-------------|
| `HF_TOKEN` | HuggingFace token for speaker diarization |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `READPILE_CONFIG` | Override config file path |

---

## Installation

```bash
pip install readpile               # base: scraping, crawling, YouTube transcription
pip install readpile[audio]        # + Whisper transcription (torch, ffmpeg-python)
pip install readpile[bot]          # + Telegram bot
pip install readpile[mcp]          # + MCP server for LLM integration
pip install readpile[all]          # everything
pip install readpile[dev]          # + test/lint tools

playwright install chromium        # required for web scraping
```

### From source

```bash
git clone https://github.com/ankurawl/readpile.git
cd readpile
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,all]"
python -m playwright install chromium
```

### System dependencies

| Dependency | Required for | Install |
|------------|-------------|---------|
| Chromium | Web scraping | `python -m playwright install chromium` (auto-managed) |
| ffmpeg | Audio transcription | `brew install ffmpeg` / `apt install ffmpeg` |

---

## Project Structure

```
src/readpile/
├── cli/             # CLI entry points (one per command)
├── scrapers/        # Article + webpage content extraction
├── transcribers/    # YouTube captions + Whisper audio transcription
├── crawlers/        # RSS, blog, and site URL discovery
├── core/            # Config, models, archiver, URL detector, robots.txt
├── bot/             # Telegram bot
└── mcp_server.py    # MCP server (FastMCP)
```

---

## Running Tests

```bash
pytest tests/ -v                                           # full suite (217 tests)
pytest tests/ -m "not slow and not network and not audio"  # fast tests only
```

---

## License

MIT — see [LICENSE](LICENSE) for details.
