# readpile

**Your personal library for the modern web.** Collect articles, transcribe videos, crawl entire blogs — then search, shortlist, and revisit anything on your own terms. Use it from the command line, or let your LLM curate your library directly via MCP.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)]()
[![Tests](https://img.shields.io/badge/tests-335%20passing-brightgreen.svg)]()

---

## What is readpile?

The best content on the web is scattered across blogs, YouTube channels, podcasts, and documentation sites. readpile brings it all into one place — your personal library. Collect anything worth keeping, search across everything you've saved, and come back to it whenever you're ready.

**The problem it solves:** You follow dozens of sources — conference talks, newsletters, technical blogs, podcast episodes, reference docs. Keeping up means clicking through pages, waiting for videos, copying text, and losing track of what you've already consumed. readpile handles the collecting so you can focus on the reading — catch up when you have time, skim what matters, save the rest for later.

### What you can do with it

- **Build your library** — Collect articles, transcripts, and documentation into a personal archive you own. Search across everything, revisit old reads, and keep a growing reference collection that's always available.
- **Build a knowledge wiki** — Let your LLM synthesize collected content into a persistent, cross-referenced wiki that compounds knowledge over time. Inspired by [Karpathy's LLMWiki concept](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).
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

**Claude Code (repo-local)** — auto-configured via `.mcp.json` at the repo root:

```bash
pip install readpile[mcp]
python -m playwright install chromium
# Claude Code discovers the server automatically when launched from this directory
```

**Claude Code (global — available from any directory):**

```bash
# 1. Install readpile globally
pip install readpile[mcp]
python -m playwright install chromium

# 2. Add to Claude Code as a global MCP server (pick one):

# Option A: Use the claude CLI
claude mcp add --scope user readpile -- readpile-mcp

# Option B: Manually edit ~/.claude.json
#   Find the "mcpServers" section and add:
#   "readpile": {
#     "command": "readpile-mcp",
#     "args": [],
#     "env": {},
#     "type": "stdio"
#   }
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
| `batch_scrape(urls, concurrency, archive_dir)` | Scrape multiple URLs in one call with concurrency control. Use `archive_dir` to save all results to disk |
| `archive(content, title, source_url, date, author, dir)` | Save content to disk as a Markdown file |
| `detect_type(url)` | Identify URL type (youtube, youtube_channel, rss, blog, audio, etc.) |
| `wiki_init(path, name, ...)` | Create a wiki with directory structure, config, and conventions |
| `wiki_save_source(content, ...)` | Save raw content to the wiki's `sources/` directory |
| `wiki_read(page, ...)` | Read a wiki page, source, or special file (index, log, conventions) |
| `wiki_write(content, ...)` | Create or update a wiki page with frontmatter validation |
| `wiki_list(...)` | List all wiki pages with metadata |
| `wiki_search(query, ...)` | Full-text search across pages and/or sources |
| `wiki_log(entry, ...)` | Append a timestamped entry to the wiki log |
| `wiki_delete(page, ...)` | Delete a wiki page and rebuild the index |

The `crawl` tool supports these modes:

| Mode | What it does |
|------|-------------|
| `auto` | Auto-detect the best mode from the URL |
| `rss` | Parse RSS/Atom feeds. Auto-discovers feeds from non-feed URLs. Use `metadata=True` to get JSON with titles, dates, descriptions |
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

### Bulk-scrape and archive a blog

Using MCP, your LLM can discover, scrape, and save an entire blog in two calls:

```
crawl("blog.example.com", mode="rss", metadata=True)
  → auto-discovers RSS feed even from the homepage
  → returns JSON metadata with title, date, author per post

batch_scrape(selected_urls, archive_dir="/path/to/library")
  → scrapes all articles and saves each as a Markdown file in one step
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

Modes: `auto`, `rss`, `blog`, `site`, `podcast`, `youtube`. Via MCP, `rss` auto-discovers feeds from non-feed URLs, `podcast` and `youtube` auto-discover feeds and return structured metadata. Blog mode returns URLs in alphabetical order; use `rss` mode for date-sorted results.

### `archive` — Save to disk

Reads ContentItems from stdin and writes Markdown files with standardized naming (`YYYY-MM-DD_title-slug.md`).

```bash
scrape https://example.com/post | archive --dir ./saved/
crawl URL | scrape --batch | archive --batch --dir ./blog/
```

### `readpile init` — Set up configuration

```bash
readpile init
# Prompts: archive by default? output directory? wiki directory?
# Writes ~/.readpile/config.toml
```

### `readpile wiki` — Wiki management

```bash
readpile wiki init ~/my-wiki --name "AI Research"      # create wiki
readpile wiki list --wiki ~/my-wiki                    # list pages
readpile wiki list --wiki ~/my-wiki --category concept # filter by category
readpile wiki search "attention" --wiki ~/my-wiki      # search pages
readpile wiki log --wiki ~/my-wiki                     # view log
readpile wiki log --wiki ~/my-wiki --recent 10         # recent entries
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

[wiki]
default_dir = ""                      # default wiki directory for MCP tools
```

| Environment Variable | Description |
|---------------------|-------------|
| `HF_TOKEN` | HuggingFace token for speaker diarization |
| `READPILE_CONFIG` | Override config file path |
| `YOUTUBE_COOKIES` | Path to a Netscape cookie file for YouTube (see [YouTube IP Blocks](#youtube-ip-blocks)) |

---

## YouTube IP Blocks

YouTube aggressively rate-limits transcript/caption requests from cloud providers, corporate networks, and VPNs. If you see errors like "YouTube is blocking transcript requests from this IP," your IP has been flagged.

readpile handles this automatically: when the fast transcript API is blocked, it falls back to `yt-dlp` with cookie authentication. You just need to provide cookies from a logged-in browser session.

### Setup (one-time)

```bash
# Export cookies from your browser (run in your regular terminal, not inside a sandbox):
yt-dlp --cookies-from-browser chrome --cookies ~/.readpile/youtube-cookies.txt https://youtube.com
```

readpile checks these locations automatically (in order):
1. `~/.readpile/youtube-cookies.txt` (recommended — just put the file here)
2. `YOUTUBE_COOKIES` environment variable pointing to a cookie file
3. `youtube_cookies` setting in `~/.readpile/config.toml`

Cookies expire periodically. Re-run the export command when you see the IP block error again.

### Browser options

Replace `chrome` with your browser: `firefox`, `safari`, `edge`, `chromium`, `opera`, or `brave`.

### Why this happens

YouTube's caption API blocks requests that don't come from a recognized browser session. The `youtube-transcript-api` library (which readpile uses for fast, free transcription) makes unauthenticated requests that YouTube increasingly rejects. Browser cookies prove you're a real user with a valid session.

---

## Installation

```bash
pip install readpile               # base: scraping, crawling, YouTube transcription
pip install readpile[audio]        # + Whisper transcription (torch, ffmpeg-python)
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

> **MCP with a venv:** The repo's `.mcp.json` uses `readpile-mcp`, which must be in PATH.
> When developing from source in a venv, Claude Code can't find the venv binary.
> Fix by updating `.mcp.json` locally:
> ```json
> { "command": ".venv/bin/readpile-mcp" }
> ```
> Or install globally alongside the venv: `pip install -e ".[mcp]"` (without the venv activated).

### System dependencies

| Dependency | Required for | Install |
|------------|-------------|---------|
| Chromium | Web scraping | `python -m playwright install chromium` (auto-managed) |
| ffmpeg | Audio transcription | `brew install ffmpeg` / `apt install ffmpeg` |

---

## Project Structure

```
src/readpile/
├── cli/             # CLI entry points (main.py parent app, wiki.py subcommands)
├── scrapers/        # Article + webpage content extraction
├── transcribers/    # YouTube captions + Whisper audio transcription
├── crawlers/        # RSS, blog, and site URL discovery
├── core/            # Config, models, archiver, URL detector, robots.txt
├── wiki/            # LLMWiki module (models.py, store.py)
└── mcp_server.py    # MCP server (FastMCP)
```

---

## Running Tests

```bash
pytest tests/ -v                                           # full suite (335 tests)
pytest tests/ -m "not slow and not network and not audio"  # fast tests only
```

---

## LLMWiki

readpile includes an LLM-maintained wiki layer inspired by [Karpathy's LLMWiki concept](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). Instead of re-deriving answers from raw documents every time, the LLM incrementally builds and maintains a structured wiki — summarizing, cross-referencing, and synthesizing sources into a compounding knowledge artifact.

### Three-layer architecture

| Layer | Owner | Purpose |
|-------|-------|---------|
| **Raw sources** | Immutable | Articles, transcripts, PDFs — saved via `wiki_save_source` |
| **The wiki** | LLM | Synthesized pages — summaries, entity pages, comparisons, explorations |
| **The schema** | User + LLM | `.wiki.toml` categories, `wiki-conventions.md` behavioral playbook |

### Wiki directory structure

```
~/my-wiki/
├── .wiki.toml              # schema: name, categories
├── wiki-conventions.md     # behavioral playbook (LLM reads this)
├── index.md                # auto-generated catalog
├── log.md                  # append-only timeline
├── sources/                # raw content (immutable)
└── pages/                  # wiki pages (LLM-maintained)
```

### Example workflows

**Ingest a URL (LLM-orchestrated via conventions file):**
```
User: "Add this to my wiki: https://example.com/article"

LLM:  wiki_read("conventions")                    → loads ingest recipe
      scrape(url)                                  → raw content + metadata
      wiki_save_source(content, ...)               → saves to sources/
      wiki_read("index")                           → current wiki state
      wiki_write(content, rebuild_index=false)      → intermediate pages
      wiki_write(content)                          → final page (rebuilds index)
      wiki_log("ingest | Title | URL\n...")         → appends to log
```

**Query the wiki:**
```
User: "What do my sources say about attention mechanisms?"

LLM:  wiki_read("index")                          → finds relevant pages
      wiki_search("attention")                     → finds additional matches
      wiki_read("attention-mechanism")             → reads the page
      Synthesizes answer, optionally files it back as an "exploration" page
```

**Lint the wiki:**
```
User: "Check my wiki for issues"

LLM:  wiki_list()                                  → all pages with metadata
      Checks for orphan pages, broken links, stale sources
      wiki_delete("old-draft")                     → removes orphan pages
      wiki_log("lint | full scan\n...")             → records findings
```

### Wiki page frontmatter

Three timestamps track the source, wiki, and page lifecycles:

```yaml
title: "Attention Mechanism"
category: concept
tags: [transformers, deep-learning]
sources: [sources/2026-05-10_article.md]
related: [transformers, andrej-karpathy]
source_date: 2026-05-08     # when the original content was published
ingested: 2026-05-10        # when added to wiki (immutable)
updated: 2026-05-17         # when page was last modified
```

### MCP tools

| Tool | Purpose |
|------|---------|
| `wiki_init` | Create wiki scaffold with conventions file |
| `wiki_save_source` | Save raw content to `sources/` |
| `wiki_read` | Read pages, sources, index, log, or conventions |
| `wiki_write` | Create/update pages with frontmatter validation. Use `rebuild_index=false` for batch writes |
| `wiki_list` | List pages with metadata, optionally filtered by category |
| `wiki_search` | Full-text search across pages and/or sources |
| `wiki_log` | Append timestamped entry to the operation log |
| `wiki_delete` | Delete a page and rebuild the index |

### Customization

The behavioral playbook (`wiki-conventions.md`) is a markdown file the LLM reads during wiki operations. Edit it to change how the LLM categorizes, cross-references, and synthesizes content. Different wikis can have different conventions.

The schema (`.wiki.toml`) defines categories and wiki identity. Default categories: `concept`, `entity`, `summary`, `comparison`, `exploration`, `reference`.

### Obsidian compatibility

The wiki works as an Obsidian vault out of the box — `[[wikilinks]]`, YAML frontmatter, and the directory structure are all native to Obsidian. Open the wiki directory in Obsidian for graph visualization and browsing while the LLM maintains the content via MCP.

---

## License

MIT — see [LICENSE](LICENSE) for details.
