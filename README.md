# mediakit

> Composable CLI toolkit for consuming media faster --
> scrape articles, transcribe videos, summarize anything.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)]()
[![Tests](https://img.shields.io/badge/tests-157%20passing-brightgreen.svg)]()

---

## Quick Start

```bash
pip install mediakit

# Summarize a YouTube video
transcribe https://youtube.com/watch?v=dQw4w9WgXcQ | summarize --length small

# Scrape and summarize a blog post
scrape https://example.com/blog/post | summarize --length medium

# One command does it all -- auto-detect, summarize, archive
content https://youtube.com/watch?v=dQw4w9WgXcQ

# Batch download an entire blog
crawl https://example.com/blog | scrape --batch | archive --dir ./blogs/
```

---

## What It Does

mediakit gives you seven composable CLI commands ("bricks") that snap
together via Unix pipes. Each brick does one thing well; combine them
to build any media consumption workflow.

```
                         +----------------+
              +--------->|   summarize    |--------> stdout / file
              |          +----------------+
              |
+-------+   +----------+                    +----------+
| crawl |-->|  scrape   |------------------->| archive  |
+-------+   +----------+                    +----------+
              |                                  ^
              |          +----------------+      |
              +--------->|  transcribe    |------+
                         +----------------+

              +----------+
              | content  |  (auto-detect + orchestrate all of the above)
              +----------+

              +----------+
              | mediakit |  init / config management
              +----------+

              +--------------+
              | content-bot  |  Telegram bot interface
              +--------------+
```

**Data flow:** Every brick reads and writes `ContentItem` objects --
a Markdown document with YAML front matter carrying metadata (title,
date, author, source URL, content type, word count). Pipe one brick
into another and they just work.

```
---
title: "How to Build CLI Tools"
source_url: https://example.com/post
content_type: article
date: 2026-04-25
author: "Jane Doe"
word_count: 2400
---

Article body text here...
```

---

## The Bricks

### `crawl` -- Discover content URLs

Finds URLs from blogs, RSS/Atom feeds, or entire websites. Outputs
one URL per line, ready to pipe into `scrape` or `transcribe`.

```bash
# Auto-detect mode (RSS, blog, or site)
crawl https://example.com/blog

# Force RSS mode, last 5 entries
crawl https://example.com/feed.xml --recent 5

# Full site crawl with depth limit
crawl https://docs.example.com --mode site --depth 3 --max-pages 50

# Blog crawl with auth (opens visible browser for login)
crawl https://members-only.com/blog --mode blog --login
```

| Flag | Default | Description |
|------|---------|-------------|
| `--mode` | `auto` | `auto`, `blog`, `site`, `rss` |
| `--depth` | `10` | Max crawl depth |
| `--max-pages` | `100` | Max pages to discover |
| `--recent N` | all | Only return N most recent (RSS) |
| `--scope` | `prefix` | `prefix` or `domain` (site mode) |
| `--login` | off | Persistent browser profile for auth |

---

### `scrape` -- Extract articles from web pages

Launches a headless Chromium browser via Playwright, extracts article
content with readability heuristics, and converts to clean Markdown.
Falls back to a generic webpage scraper for non-article pages.

```bash
# Single URL
scrape https://example.com/blog/great-post

# Batch mode -- pipe from crawl
crawl https://example.com/blog | scrape --batch

# Visible browser, skip robots.txt
scrape https://example.com/post --no-headless --no-robots
```

| Flag | Default | Description |
|------|---------|-------------|
| `--batch` | off | Read URLs from stdin, one per line |
| `--headless / --no-headless` | headless | Browser visibility |
| `--respect-robots / --no-robots` | respect | Check robots.txt |
| `--rate-limit` | `1.0` | Seconds between requests |

---

### `transcribe` -- Transcribe audio and video

Transcribes YouTube videos (via captions API), local audio/video files,
and remote media URLs. Uses YouTube captions when available; falls back
to OpenAI Whisper for everything else.

```bash
# YouTube -- uses captions API (fast, free)
transcribe https://youtube.com/watch?v=dQw4w9WgXcQ

# Local audio file -- uses Whisper
transcribe recording.mp3 --model small

# Batch transcribe from a list
crawl https://podcast.com/feed.xml | transcribe --batch

# Spanish transcript with speaker diarization
transcribe interview.wav --language es --diarize
```

| Flag | Default | Description |
|------|---------|-------------|
| `--batch` | off | Read sources from stdin |
| `--language` | `en` | Transcript language code |
| `--engine` | `auto` | `auto`, `whisper`, `whisperx` |
| `--model` | `base` | Whisper model: `tiny`, `base`, `small`, `medium`, `large` |
| `--diarize / --no-diarize` | off | Speaker diarization (needs `HF_TOKEN`) |

---

### `summarize` -- AI-powered summaries

Sends content through an LLM to produce structured summaries with
key takeaways and learnings. Supports Ollama (local, free), Claude,
OpenAI, or any OpenAI-compatible endpoint.

```bash
# Pipe from any brick
transcribe https://youtube.com/watch?v=xxx | summarize --length small

# Summarize a file
summarize notes.md --length long

# Use Claude instead of Ollama
summarize notes.md --provider claude --model claude-sonnet-4-20250514

# Batch summarize with cost confirmation
scrape --batch < urls.txt | summarize --batch --provider openai --confirm
```

| Flag | Default | Description |
|------|---------|-------------|
| `--length` | `medium` | `small` (~10%), `medium` (~20%), `long` (~40%) |
| `--provider` | `ollama` | `ollama`, `claude`, `openai`, `custom` |
| `--model` | per-provider | Model name override |
| `--batch` | off | Process batch items from stdin |
| `--confirm` | off | Confirm before paid API calls |

**Summary output structure:**

```markdown
## Summary
3-5 paragraph overview of the content.

## Key Takeaways
- Standalone, actionable bullet points.

## Learnings
- Specific facts, frameworks, and mental models.
```

---

### `archive` -- Save with standardized naming

Writes ContentItem(s) to disk as Markdown files with YAML front matter.
Filenames follow the pattern `YYYY-MM-DD_title-slug.md` with automatic
deduplication.

```bash
# Archive a single item
scrape https://example.com/post | archive --dir ./saved/

# Batch archive
crawl https://example.com/blog | scrape --batch | archive --batch --dir ./blog/
```

| Flag | Default | Description |
|------|---------|-------------|
| `--dir` | `~/mediakit-output` | Output directory |
| `--batch` | off | Process batch items from stdin |

---

### `content` -- Auto-detect and process any URL

The convenience command. Detects the source type, runs the right
extraction brick, summarizes, and archives -- all in one step.

```bash
# YouTube video -- transcribe + summarize + archive
content https://youtube.com/watch?v=dQw4w9WgXcQ

# Blog post -- scrape + summarize + archive
content https://example.com/blog/post

# Local audio -- transcribe + summarize + archive
content podcast.mp3

# Skip summarization
content https://example.com/post --no-summary

# Skip archiving, just print to stdout
content https://example.com/post --no-archive

# Batch process
content --batch < urls.txt --dir ./research/
```

| Flag | Default | Description |
|------|---------|-------------|
| `--no-summary` | off | Skip summarization |
| `--no-archive` | off | Skip archiving (stdout only) |
| `--summary-length` | `medium` | `small`, `medium`, `long` |
| `--provider` | from config | LLM provider override |
| `--model` | from config | Model override |
| `--dir` | `~/mediakit-output` | Archive directory |
| `--batch` | off | Process URLs from stdin |

---

## Composing Bricks

### Morning podcast catchup

```bash
crawl https://podcast.com/feed.xml --recent 5 \
  | transcribe --batch \
  | summarize --batch --length small
```

### Research a topic across blogs

```bash
crawl https://example.com/blog \
  | scrape --batch \
  | summarize --batch \
  | archive --dir ./research/
```

### Archive documentation

```bash
crawl https://docs.example.com --mode site --depth 3 \
  | scrape --batch \
  | archive --dir ./docs/
```

### Summarize a conference talk

```bash
transcribe https://youtube.com/watch?v=dQw4w9WgXcQ \
  | summarize --length long --provider claude
```

### Download a members-only blog

```bash
crawl https://members.example.com/blog --login \
  | scrape --batch \
  | archive --dir ./members-blog/
```

---

## Telegram Bot

mediakit includes an optional Telegram bot that lets you send URLs and
receive summaries on your phone.

### Setup

```bash
pip install mediakit[bot]

# Set required env vars
export TELEGRAM_BOT_TOKEN="your-bot-token"
export ADMIN_CHAT_ID="your-telegram-chat-id"

# Start the bot
content-bot start

# Check configuration
content-bot status
```

### Usage

Send any URL to the bot and it will auto-detect the content type,
extract the text, summarize it, and reply with:

1. A formatted summary message
2. A downloadable Markdown document with the full transcript/text

### Bot commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | List available commands |
| `/whoami` | Show your chat ID |
| `/set_language <code>` | Set transcript language (e.g., `en`, `es`, `hi`) |
| `/set_style <brief\|detailed>` | Set summary style |
| `/history` | Show recently processed items |
| `/admin_add <chat_id>` | Add user to whitelist (admin only) |
| `/admin_remove <chat_id>` | Remove user from whitelist (admin only) |
| `/admin_list` | Show whitelisted users (admin only) |

---

## Configuration

### Initialize config

```bash
mediakit init
# Creates ~/.mediakit/config.toml with commented defaults
```

### Config file reference

```toml
# ~/.mediakit/config.toml

[general]
output_dir = "~/mediakit-output"       # default archive directory
date_format = "YYYY-MM-DD"             # filename date format
filename_max_length = 80               # max filename slug length

[summarize]
provider = "ollama"                    # "ollama" | "claude" | "openai" | "custom"
default_length = "medium"              # "small" | "medium" | "long"

[summarize.ollama]
model = "llama3.2"                     # any Ollama model name
host = "http://localhost:11434"        # Ollama server URL

[summarize.claude]
model = "claude-sonnet-4-20250514"     # Claude model ID

[summarize.openai]
model = "gpt-4o"                       # OpenAI model ID

[summarize.custom]
endpoint = ""                          # OpenAI-compatible endpoint URL
model = ""                             # model name at that endpoint

[transcribe]
engine = "auto"                        # "auto" | "whisper" | "whisperx"
whisper_model = "base"                 # "tiny" | "base" | "small" | "medium" | "large"
diarize = false                        # speaker diarization (requires HF_TOKEN)

[scrape]
headless = true                        # run browser in headless mode
respect_robots = true                  # check robots.txt before scraping
rate_limit = 1.0                       # seconds between requests

[crawl]
max_depth = 10                         # max crawl depth for site mode
max_pages = 100                        # max pages to discover

[bot]
whitelist_file = "~/.mediakit/whitelist.json"
preferences_file = "~/.mediakit/preferences.json"
```

### Environment variables

| Variable | Maps to | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | `summarize.claude.api_key` | Anthropic API key |
| `OPENAI_API_KEY` | `summarize.openai.api_key` | OpenAI API key |
| `MEDIAKIT_LLM_API_KEY` | `summarize.custom.api_key` | Custom endpoint key |
| `HF_TOKEN` | `transcribe.hf_token` | HuggingFace token (diarization) |
| `TELEGRAM_BOT_TOKEN` | `bot.token` | Telegram bot token |
| `OLLAMA_HOST` | `summarize.ollama.host` | Ollama server URL |
| `MEDIAKIT_CONFIG` | -- | Override config file path |

### Precedence (highest wins)

1. CLI flags (`--provider claude`)
2. Environment variables (`ANTHROPIC_API_KEY`)
3. Config file (`~/.mediakit/config.toml`)
4. Built-in defaults

---

## Installation

### pip (recommended)

```bash
pip install mediakit              # base: scraping, crawling, YouTube transcription
pip install mediakit[audio]       # + Whisper transcription (torch, ffmpeg-python)
pip install mediakit[bot]         # + Telegram bot
pip install mediakit[claude]      # + Anthropic Claude provider
pip install mediakit[openai]      # + OpenAI provider
pip install mediakit[all]         # everything
```

### From source

```bash
git clone https://github.com/your-username/mediakit.git
cd mediakit
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,all]"
playwright install chromium
```

### System dependencies

| Dependency | What needs it | macOS | Ubuntu/Debian |
|------------|--------------|-------|---------------|
| ffmpeg | Audio transcription | `brew install ffmpeg` | `sudo apt install ffmpeg` |
| Chromium | Scraping (auto-installed) | `playwright install chromium` | `playwright install chromium` |
| Ollama | Local summarization | `brew install ollama` | [ollama.com/download](https://ollama.com/download) |

---

## Architecture

```
src/mediakit/
|
|-- core/                      # Shared infrastructure
|   |-- models.py              # ContentItem dataclass + serialization
|   |-- config.py              # TOML config loader with env overlay
|   |-- detector.py            # URL type detection (YouTube, RSS, audio, etc.)
|   |-- archiver.py            # Filename generation + file writing
|   |-- cache.py               # Response caching
|   +-- robots.py              # robots.txt checker
|
|-- crawlers/                  # URL discovery
|   |-- rss.py                 # RSS/Atom feed parser
|   |-- blog.py                # Playwright-based blog crawler
|   +-- site.py                # Recursive site crawler
|
|-- scrapers/                  # Content extraction
|   |-- article.py             # Readability-based article extractor
|   +-- webpage.py             # Generic webpage scraper (fallback)
|
|-- transcribers/              # Audio/video transcription
|   |-- youtube.py             # YouTube captions API
|   +-- audio.py               # Whisper-based transcription
|
|-- summarizer/                # LLM summarization
|   |-- engine.py              # Prompt building, chunking, synthesis
|   +-- providers.py           # LLM adapters (Ollama, Claude, OpenAI, custom)
|
|-- bot/                       # Telegram bot
|   |-- main.py                # Bot entry point + handler registration
|   |-- handlers.py            # Command and message handlers
|   |-- whitelist.py           # User access control
|   |-- preferences.py         # Per-user settings (language, style)
|   +-- telegram_formatter.py  # Message formatting
|
+-- cli/                       # CLI entry points (one per brick)
    |-- crawl.py               # crawl command
    |-- scrape.py              # scrape command
    |-- transcribe.py          # transcribe command
    |-- summarize.py           # summarize command
    |-- archive.py             # archive command
    |-- content.py             # content command (orchestrator)
    |-- init.py                # mediakit init
    +-- bot.py                 # content-bot command
```

### ContentItem data model

The `ContentItem` dataclass is the universal data format. Every brick
produces and/or consumes it. It serializes to YAML front matter +
Markdown body, and deserializes from the same format via stdin.

Batch operations use `---CONTENT_ITEM---` as a delimiter between
items.

### LLM provider pattern

All LLM providers implement the `LLMProvider` abstract base class with
a single `generate(prompt) -> str` method. Adding a new provider means:

1. Subclass `LLMProvider` in `providers.py`
2. Add the config section to `DEFAULTS` in `config.py`
3. Add the dispatch case in `get_provider()`

---

## Contributing

### Adding a new scraper

1. Create `src/mediakit/scrapers/your_scraper.py`
2. Implement a function that takes a URL/HTML and returns a `ContentItem`
3. Wire it into `cli/scrape.py` (detection + fallback logic)
4. Add tests in `tests/test_your_scraper.py`

### Adding a new transcriber

1. Create `src/mediakit/transcribers/your_transcriber.py`
2. Implement a function that returns a `ContentItem` with the transcript
3. Add detection logic in `core/detector.py` if needed
4. Wire it into `cli/transcribe.py`
5. Add tests

### Adding a new LLM provider

1. Subclass `LLMProvider` in `summarizer/providers.py`
2. Add config defaults in `core/config.py` under `DEFAULTS["summarize"]`
3. Add env var mapping in `core/config.py` `ENV_MAP` if needed
4. Add the dispatch case in `get_provider()`
5. Add tests in `tests/test_providers.py`

### Running tests

```bash
# All tests (skip slow, network, and audio tests)
pytest tests/ -v -m "not slow and not network and not audio"

# Full suite
pytest tests/ -v

# With coverage
pytest tests/ --cov=mediakit --cov-report=term-missing
```

### Linting

```bash
ruff check src/ tests/
```

---

## License

MIT -- see [LICENSE](LICENSE) for details.
