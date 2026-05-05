# mediakit

**Convert any media into readable text — in seconds.** Scrape articles, transcribe YouTube videos, crawl entire blogs, and archive everything as Markdown. Use it from the command line, or let your LLM call it directly via MCP.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)]()
[![Tests](https://img.shields.io/badge/tests-157%20passing-brightgreen.svg)]()

---

## What is mediakit?

mediakit turns web content into clean, structured text you can actually work with. Point it at a URL — a blog post, a YouTube video, a podcast RSS feed, a documentation site — and it gives you back Markdown with metadata, ready to read, search, summarize, or feed into any workflow.

**The problem it solves:** You want to consume a 45-minute conference talk, catch up on 20 blog posts from last week, or archive an entire documentation site before it goes offline. Doing this manually means clicking through pages, copying text, waiting for videos, and losing formatting. mediakit automates all of that — the browser rendering, the transcript extraction, the feed parsing, the file organization — so you get straight to the content.

### What you can do with it

- **Catch up fast** — Pull the last 10 posts from a blog, 5 episodes from a podcast feed, or a full YouTube playlist. Pipe them into your LLM and ask for a single consolidated briefing.
- **Build a personal knowledge base** — Archive articles, transcripts, and documentation as searchable Markdown files. Everything gets clean filenames, dates, and metadata automatically.
- **Give your LLM eyes and ears** — Connect mediakit as an MCP server and your AI assistant can read any webpage, watch any YouTube video, or crawl any site on demand.
- **Create custom digests** — Combine content from multiple sources (RSS feeds + blog crawls + video transcripts) into a single stream, then process it however you want — summarize, translate, extract action items, generate study notes.
- **Research at scale** — Crawl an entire documentation site or blog archive, extract every page, and have it all in one local directory as Markdown files you can grep, analyze, or feed to an LLM.

### What it can extract

| Source | What you get |
|--------|-------------|
| **Blog posts & articles** | Clean Markdown with title, author, date, tags — extracted from the rendered page |
| **YouTube videos** | Full transcript with timestamps, via YouTube's caption API (instant, free) |
| **Audio & video files** | Whisper-powered transcription with optional speaker diarization |
| **RSS/Atom feeds** | All entry URLs, ready to pipe into scrape or transcribe |
| **Documentation sites** | Recursive crawl that discovers every page under a URL prefix |
| **Any webpage** | Headless Chromium rendering + intelligent content extraction |

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

Tools output **ContentItems** — Markdown documents with YAML front matter — that pipe cleanly between commands, work with any Markdown viewer, and are easy for LLMs to parse:

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
pip install mediakit
playwright install chromium    # needed for web scraping
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

mediakit ships as an [MCP server](https://modelcontextprotocol.io/) that any compatible LLM client can discover and use. Once connected, your LLM can scrape pages, transcribe videos, crawl sites, and archive content — then use its own intelligence to summarize, compare, translate, or do whatever you ask.

**Claude Code** — auto-configured via `.mcp.json` at the repo root:

```bash
pip install mediakit[mcp]
# Claude Code discovers the server automatically
```

**Other MCP clients** — add to your client's MCP configuration:

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

Available MCP tools:

| MCP Tool | What it does |
|----------|-------------|
| `scrape(url)` | Extract article/webpage content as Markdown |
| `transcribe(source, language)` | Transcribe YouTube or audio/video URLs |
| `crawl(url, mode, recent, limit)` | Discover content URLs from feeds, blogs, or sites |
| `archive(content, title, source_url)` | Save content to disk as a Markdown file |
| `detect_type(url)` | Identify URL type (youtube, rss, blog, audio, etc.) |

---

## Example Workflows

### Morning briefing from multiple sources

```bash
# Pull recent posts from 3 blogs + a podcast, combine into one stream
{
  crawl https://blog-a.com/feed.xml --recent 3 | scrape --batch
  crawl https://blog-b.com/blog | scrape --batch
  transcribe https://youtube.com/watch?v=latest-talk
} | archive --batch --dir ./daily-briefing/
# Then ask your LLM: "Summarize today's briefing into 5 bullet points"
```

### Archive a blog before it disappears

```bash
crawl https://closing-soon.com/blog | scrape --batch | archive --dir ./saved-blog/
# Every post saved as YYYY-MM-DD_title-slug.md with full metadata
```

### Research a topic across sources

```bash
# Crawl docs, grab relevant videos, pull it all into one folder
crawl https://docs.example.com --mode site --depth 3 | scrape --batch | archive --dir ./research/
transcribe https://youtube.com/watch?v=related-talk | archive --dir ./research/
# Now you have a complete research folder to analyze
```

### Catch up on a podcast

```bash
crawl https://podcast.com/feed.xml --recent 5
# Returns 5 episode URLs — pipe to transcribe, then ask your LLM for highlights
```

### Download behind a login wall

```bash
crawl https://members.example.com/blog --login | scrape --batch | archive --dir ./members/
# Opens a real browser for you to log in, then crawls with your session
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
| `--dir` | `~/mediakit-output` | Output directory when archiving |
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

Finds URLs from RSS/Atom feeds, blogs (via Playwright), or full site crawls. Outputs one URL per line.

```bash
crawl https://example.com/blog                       # auto-detect mode
crawl https://example.com/feed.xml --recent 5        # RSS, 5 most recent
crawl https://docs.example.com --mode site --depth 3 # recursive site crawl
crawl https://members.example.com --mode blog --login # auth via persistent browser
```

### `archive` — Save to disk

Reads ContentItems from stdin and writes Markdown files with standardized naming (`YYYY-MM-DD_title-slug.md`).

```bash
scrape https://example.com/post | archive --dir ./saved/
crawl URL | scrape --batch | archive --batch --dir ./blog/
```

### `mediakit init` — Set up configuration

```bash
mediakit init
# Prompts: archive by default? output directory?
# Writes ~/.mediakit/config.toml
```

### `content-bot` — Telegram bot

```bash
content-bot start     # start the bot
content-bot status    # check if configured
```

---

## Archiving

By default, content goes to stdout. Opt in to saving files with `--archive` or by setting `auto_archive = true` in config.

| Command | `auto_archive = false` (default) | `auto_archive = true` |
|---------|----------------------------------|----------------------|
| `content URL` | stdout only | stdout + save to file |
| `content URL --archive` | stdout + save | stdout + save |
| `content URL --no-archive` | stdout only | stdout only |
| MCP `archive()` | always saves (explicit call) | always saves |

---

## Telegram Bot

An optional Telegram bot — send it any URL and get back extracted content as a formatted message plus a downloadable Markdown document.

```bash
pip install mediakit[bot]
export TELEGRAM_BOT_TOKEN="your-bot-token"
export ADMIN_CHAT_ID="your-telegram-chat-id"
content-bot start
```

Supports `/set_language`, `/set_style brief|detailed`, `/history`, and admin whitelist commands.

---

## Configuration

```bash
mediakit init    # interactive setup, writes ~/.mediakit/config.toml
```

```toml
[general]
output_dir = "~/mediakit-output"      # where archived files go
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
| `MEDIAKIT_CONFIG` | Override config file path |

---

## Installation

```bash
pip install mediakit               # base: scraping, crawling, YouTube transcription
pip install mediakit[audio]        # + Whisper transcription (torch, ffmpeg-python)
pip install mediakit[bot]          # + Telegram bot
pip install mediakit[mcp]          # + MCP server for LLM integration
pip install mediakit[all]          # everything
pip install mediakit[dev]          # + test/lint tools

playwright install chromium        # required for web scraping
```

### From source

```bash
git clone https://github.com/anthropics/mediakit.git
cd mediakit
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,all]"
playwright install chromium
```

### System dependencies

| Dependency | Required for | Install |
|------------|-------------|---------|
| Chromium | Web scraping | `playwright install chromium` (auto-managed) |
| ffmpeg | Audio transcription | `brew install ffmpeg` / `apt install ffmpeg` |

---

## Project Structure

```
src/mediakit/
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
pytest tests/ -v                                           # full suite (157 tests)
pytest tests/ -m "not slow and not network and not audio"  # fast tests only
```

---

## License

MIT — see [LICENSE](LICENSE) for details.
