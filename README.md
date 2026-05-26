# readpile

**Collect anything from the web. Let your LLM turn it into a knowledge base that grows smarter over time.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)]()

---

## What is readpile?

You follow dozens of sources — conference talks, newsletters, technical blogs, podcast episodes, reference docs. The problem isn't finding content. It's that nothing compounds. You read an article, forget where you saw it, re-derive the same conclusions next month, and never build on what you've already consumed.

readpile fixes this. It extracts content from anywhere on the web — articles, videos, podcasts, documentation sites — and feeds it into an LLM-maintained wiki that accumulates knowledge over time. Cross-references are built automatically. Contradictions between sources are flagged. Your explorations compound: good answers get filed back as new wiki pages, so future questions benefit from past ones.

Humans abandon wikis because the maintenance burden grows faster than the value. LLMs don't get bored, don't forget to update a cross-reference, and can touch 15 files in one pass. Your job is to curate sources, direct the analysis, and ask good questions. The LLM handles the bookkeeping.

readpile is the plumbing that makes this work — content extraction, feed monitoring, email-driven collection, and a wiki toolkit — all exposed as both CLI commands and MCP tools that any LLM can use.

### How it fits together

```
 COLLECT                    EXTRACT                    STORE
────────────────────────────────────────────────────────────────
 email inbox ──┐             ┌── scrape ───┐          source files
 RSS feeds ────┤             │             │          (raw content)
 YouTube ──────┼── sync ─────┼─ transcribe ┼────→         │
 podcasts ─────┤   or manual │             │          wiki pages
 URLs ─────────┘             └── crawl ────┘          (synthesized)
```

**Collect** from any source — email newsletters, RSS feeds, YouTube channels, podcasts, or individual URLs. The sync pipeline automates collection; you can also use CLI commands or MCP tools directly.

**Extract** content using the right tool for the job — `scrape` for articles, `transcribe` for video/audio, `crawl` to discover URLs from feeds and sites.

**Store** as source files (raw extracted content, immutable) and wiki pages (LLM-synthesized, cross-referenced, continuously updated).

---

## Design Philosophy

**Content extraction has no built-in LLM.** Scraping, transcription, crawling, and wiki file I/O are pure code — no API keys needed, works with any MCP client. The sync pipeline is the exception: it calls an LLM API directly for automated digest grouping and wiki synthesis, so it does require an API key (stored in `config.toml`).

**Thin tools + conventions file.** The wiki tools handle file I/O and validation, not workflow orchestration. Behavioral rules — how to categorize, cross-reference, and synthesize — live in `wiki-conventions.md`, a markdown file the LLM reads as a prompt. Changing wiki behavior means editing markdown, not Python. Different wikis can have different conventions.

**Two modes of operation.** For interactive use, MCP tools let your LLM orchestrate the full workflow — scrape, save, synthesize, cross-reference — guided by the conventions file. For hands-off use, the sync pipeline automates collection and synthesis on a schedule, driven entirely through email.

**Three timestamps on wiki pages.** `source_date` is when the original content was published. `ingested` is when you added it to the wiki. `updated` is when the wiki page was last revised. Without `source_date`, all information gets flattened into a timeless present — the LLM can't distinguish a 2024 claim from a 2026 one.

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/ankurawl/readpile.git
cd readpile
pip install -e ".[all]"                         # everything: scraping, MCP, sync, audio
python -m playwright install chromium           # one-time: downloads the browser for web scraping
```

For audio/video transcription (podcasts, local files), also install ffmpeg:

```bash
brew install ffmpeg       # macOS
# apt install ffmpeg      # Linux
```

If you only need specific features:

```bash
pip install -e "."              # base: scraping, crawling, YouTube transcription
pip install -e ".[mcp]"         # + MCP server for LLM integration
pip install -e ".[sync]"        # + sync pipeline (email, feeds, digest, synthesis)
pip install -e ".[audio]"       # + Whisper transcription (torch, ffmpeg-python)
```

### 2. Try it (zero config)

These work immediately — no setup needed. Wrap URLs in quotes to avoid shell issues with `?` and `&` characters:

```bash
scrape "https://example.com/blog/post"        # extract an article as markdown
transcribe "https://youtube.com/watch?v=..."   # get a full transcript
crawl "https://example.com/blog"               # discover all post URLs
content "https://example.com/post"                # auto-detect and extract
```

### 3. Set up your knowledge base

Before running `readpile init`, have these ready:

| What                                                                                                   | Why                                                            | Required?                               |
| ------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------- | --------------------------------------- |
| A wiki directory path (e.g. `~/my-wiki`)                                                               | Where your knowledge base lives                                | Yes                                     |
| An LLM API key ([Anthropic](https://console.anthropic.com/), [Google AI Studio](https://aistudio.google.com/), [OpenAI](https://platform.openai.com/), [OpenRouter](https://openrouter.ai/), etc.) | Powers digest grouping and wiki synthesis in the sync pipeline | Yes, unless using a local model |
| A dedicated Gmail address (e.g. `readpile-inbox@gmail.com`)                                            | Collects newsletters and forwarded links                       | No — only if you want email-driven sync |
| A [Gmail App Password](https://myaccount.google.com/apppasswords) for that Gmail account               | Lets readpile send you digest emails from the readpile inbox   | No — only if you enable email           |
| [Gmail OAuth credentials](https://console.cloud.google.com/) (JSON file)                               | Lets readpile read that inbox                                  | No — only if you enable email           |

```bash
readpile init
```

This walks you through configuration interactively — including creating your wiki and setting your API keys. You can re-run `readpile init` at any time to change your settings.

After init, add feeds. These serve double duty — they define what the sync pipeline crawls for new content **and** which email senders are trusted (see [Trusted senders](#trusted-senders)):

```bash
readpile feeds add "https://blog.example.com"        # auto-detects RSS feed
readpile feeds add "https://youtube.com/@3blue1brown" # YouTube channel
readpile feeds add "https://acquired.fm"              # podcast
```

### 4. Connect to your LLM

readpile ships as an [MCP server](https://modelcontextprotocol.io/) so any compatible LLM can use its tools directly.

**Claude Code (global — available from any directory):**

```bash
claude mcp add --scope user readpile -- readpile-mcp
```

**Claude Code (repo-local):** auto-configured via `.mcp.json` at the repo root.

**Other MCP clients:**

```json
{
  "mcpServers": {
    "readpile": { "command": "readpile-mcp", "args": [], "type": "stdio" }
  }
}
```

### 5. Automate

Schedule two cron jobs and you're done — everything else happens through email:

```bash
crontab -e
# 0 8  * * *  readpile sync                  # morning: collect + send digest
# 0 20 * * *  readpile synthesize --pending   # evening: build wiki pages
```

Each morning, `readpile sync` checks your email inbox and feeds for new content, saves source files to the wiki, and sends you a digest email. Reply to the digest to approve or skip synthesis. Each evening, `readpile synthesize` turns approved items into wiki pages.

---

## Tools

Every capability is available both as a CLI command and as an MCP tool. The CLI is useful for shell scripts and one-off tasks. The MCP tools let your LLM use readpile directly.

### Content extraction

| Capability | CLI | MCP | Description |
|------------|-----|-----|-------------|
| Extract articles | `scrape URL` | `scrape(url)` | Clean markdown from any webpage. Headless Chromium with readability heuristics, HTTP fallback |
| Transcribe | `transcribe URL` | `transcribe(source, language, fallback_url)` | YouTube captions (instant) or Whisper for audio/video. `fallback_url` checks for YouTube embeds when audio fails |
| Discover URLs | `crawl URL` | `crawl(url, mode, recent, limit, metadata)` | Find content from RSS feeds, blogs, sites, YouTube channels, or podcasts |
| Detect type | — | `detect_type(url)` | Identify URL type: youtube, rss, blog, audio, etc. |
| Auto-detect | `content URL` | — | Detect URL type and route to scrape or transcribe automatically |
| Batch scrape | — | `batch_scrape(urls, concurrency)` | Scrape multiple URLs in one call |

### Wiki

| Capability | CLI | MCP | Description |
|------------|-----|-----|-------------|
| Create wiki | `readpile init` or `readpile wiki init PATH` | `wiki_init(path, name, ...)` | `readpile init` creates one automatically; use `wiki init` for additional wikis |
| Save source file | — | `wiki_save_source(content, title, ...)` | Save raw content to the wiki's `sources/` directory |
| Read | — | `wiki_read(page)` | Read a wiki page, source file, index, log, or conventions |
| Write | — | `wiki_write(content, page, rebuild_index)` | Create or update a wiki page with frontmatter validation |
| List pages | `readpile wiki list` | `wiki_list(category)` | List all wiki pages with metadata |
| Search | `readpile wiki search QUERY` | `wiki_search(query, scope)` | Full-text search across pages and/or source files |
| Log | `readpile wiki log` | `wiki_log(entry)` | Append a timestamped entry to the operation log |
| Delete | — | `wiki_delete(page)` | Delete a wiki page and rebuild the index |

### Sync pipeline

| Capability | CLI | Description |
|------------|-----|-------------|
| Sync | `readpile sync` | Check email + feeds, save source files, send digest |
| Synthesize | `readpile synthesize --pending` | LLM-powered wiki page creation from approved source files |
| Add feed | `readpile feeds add URL` | Auto-detect type and add (or update) a feed |
| List feeds | `readpile feeds list` | Show all feeds with indices and status |
| Remove feed | `readpile feeds remove IDS` | Remove feed(s) by index (e.g. `1,3-5`) or name |
| Enable feed | `readpile feeds enable NAME` | Re-enable a disabled feed |
| Status | `readpile status` | Overview: last sync, pending count, feed health |

### Crawl modes

The `crawl` tool supports multiple discovery modes:

| Mode | What it does |
|------|-------------|
| `auto` | Auto-detect the best mode from the URL |
| `rss` | Parse RSS/Atom feeds. Auto-discovers feeds from non-feed URLs. Use `metadata=True` for JSON with titles, dates, descriptions |
| `podcast` | Auto-discover podcast RSS feed from any URL, filter to audio-only episodes |
| `youtube` | Resolve YouTube channel URLs to their RSS feed, return recent videos |
| `blog` | Discover blog post URLs via Playwright or HTTP fallback. Returns alphabetical order; use `rss` for date-sorted |
| `site` | Recursive site crawl under a URL prefix |

---

## Example Workflows

### Add an article to your wiki

```
You:  "Add this to my wiki: https://example.com/how-attention-works"

LLM:  [reads wiki conventions]
      [scrapes the article → gets title, author, date, full text]
      [saves to sources/2026-05-19_how-attention-works.md]
      [reads wiki index → finds related pages: transformers.md, neural-networks.md]
      [creates pages/attention-mechanism.md with cross-references]
      [updates pages/transformers.md with new "Attention" section]
      [logs: "ingest | How Attention Works | example.com"]

Done — created attention-mechanism.md and updated transformers.md.
```

### Query your wiki

```
You:  "What do my sources say about the differences between GPT and BERT?"

LLM:  [reads wiki index → finds gpt.md, bert.md, transformers.md]
      [searches for "GPT BERT" → finds 2 more relevant pages]
      [reads all 5 pages, synthesizes comparison]

GPT and BERT differ in three key ways: [answer based on your wiki]...

      [files answer back as pages/gpt-vs-bert.md with category "exploration"]
```

### Catch up via email

```
 8:00 AM  readpile sync runs via cron
          → checks your email inbox (2 newsletters arrived overnight)
          → crawls your 5 RSS feeds (3 new posts)
          → transcribes 1 new YouTube video from a subscribed channel
          → sends you a digest email: "readpile — May 19 (6 new items)"

10:30 AM  You read the digest on your phone and reply:
          "Synthesize items 1, 3, and 5. Skip item 2.
           Add https://newblog.com to my feeds."

 8:00 PM  readpile synthesize runs via cron
          → processes your reply: marks 1, 3, 5 for synthesis, skips 2
          → adds newblog.com as an RSS feed
          → reads each source file, compares against existing wiki
          → creates 2 new wiki pages, updates 1 existing page
          → skips item 5 (redundant with existing pages/ml-training.md)
```

### Bulk-ingest a blog

```
You:  "Save every post from blog.example.com to my wiki"

LLM:  [crawls blog.example.com, mode=rss → discovers RSS feed]
      [finds 47 posts with titles, dates, authors]
      [batch_scrape all 47 URLs → full content]
      [wiki_save_source for each article → saves to sources/]
      [logs: "bulk ingest | blog.example.com | 47 source files saved"]

Saved 47 posts to sources/. They'll appear in your next digest,
or I can start synthesizing them into wiki pages now.
```

### Search across everything

```
You:  "Search my wiki for anything about backpropagation"

LLM:  [wiki_search("backpropagation", scope="all")]
      Found 3 results:
      - pages/backpropagation.md — "Backpropagation" [concept]
        Line 12: "...the chain rule applied recursively through layers..."
      - pages/neural-network-training.md — "Neural Network Training" [summary]
        Line 28: "...backpropagation computes gradients for each weight..."
      - sources/2026-05-10_karpathy-lecture.md
        Line 145: "...backprop is just repeated application of the chain rule..."
```

### Crawl with a login session

The `crawl` CLI supports a `--login` flag that opens a visible browser window so you can log in manually. The crawl then runs with your authenticated session:

```bash
crawl https://members.example.com/blog --login
# Opens Chrome → you log in → crawl discovers URLs with your session
```

Note: `--login` applies to URL discovery only (the `crawl` step). The discovered URLs are printed to stdout — scraping the actual content behind the login wall would require the pages to be accessible without authentication, or using the URLs in another tool that supports auth.

---

## Sync Pipeline

Automated content collection and knowledge synthesis, driven entirely through email after initial setup.

### Daily flow

```
 MORNING (cron)                          YOU (anytime)                    EVENING (cron)
┌─────────────────────┐    ┌──────────────────────────┐    ┌──────────────────────────┐
│ readpile sync       │    │ Read digest on phone.    │    │ readpile synthesize      │
│                     │    │ Reply:                   │    │   --pending              │
│ 1. Process replies  │    │ "Synthesize 1 and 3.    │    │                          │
│ 2. Check email      │───→│  Skip 2. Add            │───→│ Processes approved items │
│ 3. Crawl feeds      │    │  https://newblog.com     │    │ into wiki pages.         │
│ 4. Send digest      │    │  to my feeds."           │    │ Items with no reply      │
└─────────────────────┘    └──────────────────────────┘    │ auto-synthesize after    │
                                                           │ 7 days.                  │
                                                           └──────────────────────────┘
```

### How it handles content

| Source type | What happens |
|-------------|-------------|
| **Newsletter email** | HTML extracted, converted to markdown via the article scraper |
| **Forwarded URL** | URL extracted from email body, scraped normally |
| **RSS/Atom feed** | New entries scraped as articles |
| **YouTube channel** | New videos transcribed via captions API |
| **Podcast** | Tries YouTube embed on episode page first (instant); falls back to Whisper audio transcription |

### Digest email

The daily digest groups new items into 3-5 topics (via LLM) and sends them as markdown attachments. Reply to control synthesis:

- *"Synthesize items 1, 3, 4"* — immediate synthesis on next run
- *"Skip item 2"* — never synthesize
- *"Add https://newblog.com to my feeds"* — adds a feed
- *"Remove Old Blog from feeds"* — removes a feed
- No reply? Items auto-synthesize after 7 days.

### Deduplication

The same article arriving via both email newsletter and RSS feed is saved only once. URLs are normalized (tracking params stripped, trailing slashes removed, `www.` prefix removed) before comparison. Email content takes priority over feed excerpts when both exist.

### Trusted senders

The sync pipeline only processes emails from **trusted senders** — everything else is silently skipped. This prevents spam, notifications, and other noise from entering your wiki. A sender is trusted if any of the following match:

| Rule | Example |
|------|---------|
| Sender's domain matches a configured feed | You added `https://blog.example.com` → emails from `newsletter@example.com` are trusted |
| Sender is from a known newsletter platform | Substack, Beehiiv, ConvertKit, Buttondown, Mailchimp, Ghost, MailerLite |
| Sender is listed in `skip_synthesis_senders` | `skip_synthesis_senders = ["friend@gmail.com"]` in `[sync.email]` config |

If `readpile sync` reports `0 email` but you know there are messages in the inbox, the sender probably isn't trusted. To fix it:

- **For newsletters:** add the publication as a feed — `readpile feeds add "https://newsletter-site.com"`. This trusts all email from that domain.
- **For individual senders:** add them to `skip_synthesis_senders` in `~/.readpile/config.toml`:
  ```toml
  [sync.email]
  skip_synthesis_senders = ["friend@gmail.com", "coworker@company.com"]
  ```

Run `readpile sync -v` to see which senders are being skipped (`Unknown sender skipped: ...`).

---

## LLMWiki

The wiki is a persistent, compounding artifact — not a disposable summary. The LLM pre-compiles knowledge once, then keeps it current, rather than re-deriving synthesis on every question. Cross-references are already there. Contradictions have already been flagged. Inspired by [Andrej Karpathy's LLMWiki concept](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

Obsidian is the IDE; the LLM is the programmer; the wiki is the codebase.

### Three-layer architecture

| Layer | Owner | Purpose |
|-------|-------|---------|
| **Source files** | Immutable | Articles, transcripts, PDFs — saved via `wiki_save_source`. The raw material the LLM reads from |
| **Wiki pages** | LLM | Synthesized pages — summaries, entity pages, comparisons, explorations. Created and updated via `wiki_write` |
| **Schema** | User + LLM | `.wiki.toml` (categories, wiki identity) and `wiki-conventions.md` (behavioral playbook the LLM reads as a prompt) |

### Wiki directory structure

```
~/my-wiki/
├── .wiki.toml              # schema: name, categories
├── wiki-conventions.md     # behavioral playbook (LLM reads this)
├── index.md                # auto-generated catalog (never edit manually)
├── log.md                  # append-only timeline of operations
├── sources/                # source files — raw extracted content (immutable)
└── pages/                  # wiki pages — LLM-synthesized (continuously updated)
```

### Wiki page frontmatter

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

### Customization

Edit `wiki-conventions.md` to change how the LLM categorizes, cross-references, and synthesizes content. Different wikis can have different conventions — an AI research wiki might want aggressive cross-referencing; a reading log might want minimal structure.

The schema (`.wiki.toml`) defines categories. Defaults: `concept`, `entity`, `summary`, `comparison`, `exploration`, `reference`.

### Obsidian compatibility

The wiki works as an Obsidian vault out of the box — `[[wikilinks]]`, YAML frontmatter, and the directory structure are all native to Obsidian. Open the wiki directory in Obsidian for graph visualization and browsing while the LLM maintains the content via MCP.

---

## Configuration

### Main config (`~/.readpile/config.toml`)

Generated by `readpile init`. Re-run `readpile init` at any time to regenerate with new values. All settings have sensible defaults.

```toml
[general]
date_format = "YYYY-MM-DD"
filename_max_length = 80

[scrape]
headless = true
respect_robots = true
rate_limit = 1.0                  # seconds between requests

[crawl]
max_depth = 10
max_pages = 100

[transcribe]
engine = "auto"                   # "auto" | "whisper" | "whisperx"
whisper_model = "base"            # "tiny" | "base" | "small" | "medium" | "large"
diarize = false                   # speaker diarization (requires hf_token)

[wiki]
default_dir = ""                  # default wiki directory for MCP tools

[llm]
base_url = "anthropic"            # shortcut or full URL (see below)
model = "claude-sonnet-4-6"
api_key = "sk-..."

# Shortcuts: "anthropic", "openai" (empty — SDK default), "gemini",
#            "openrouter", "ollama" (localhost:11434)
# Or any OpenAI-compatible URL: "https://my-proxy.example.com/v1"
#
# Examples:
#   base_url = "gemini"             model = "gemini-2.0-flash"
#   base_url = "openrouter"         model = "google/gemini-2.0-flash"
#   base_url = "ollama"             model = "llama3"
#   base_url = ""                   model = "gpt-4o"  (OpenAI default)

[sync]
synthesis_wait_days = 7           # days before auto-synthesizing unreplied items
max_auto_synthesize_per_run = 20  # cap per run (oldest first)

[sync.email]
enabled = true
provider = "gmail"
account = "readpile-inbox@gmail.com"
# Gmail OAuth: download credentials JSON to ~/.readpile/email-credentials.json
# First run opens browser for consent; token cached automatically after that
# Emails from unknown senders are silently skipped. Trust senders by either:
# - Adding their domain as a feed (readpile feeds add URL), or
# - Listing them here:
# skip_synthesis_senders = ["friend@gmail.com"]

[sync.digest]
enabled = true
to = "personal@email.com"
from = "readpile-inbox@gmail.com"
smtp_password = "..."             # Gmail App Password for the inbox account
# This is the App Password for the READPILE email account (the "from" address),
# NOT your personal email. It lets readpile send digests from that inbox.
# Requires 2FA enabled on the account, then generate at:
# Google Account → Security → App Passwords
```

### Feeds (`~/.readpile/feeds.toml`)

Machine-managed via `readpile feeds` commands. Kept separate so feed management never touches your hand-edited settings.

```toml
[[feeds]]
name = "Example Blog"
url = "https://blog.example.com/feed/"
kind = "rss"

[[feeds]]
name = "3Blue1Brown"
url = "https://youtube.com/@3blue1brown"
kind = "youtube"

[[feeds]]
name = "Weekly Roundup"
url = "https://roundup.example.com/feed/"
kind = "rss"
synthesize = false    # save source files but skip wiki synthesis
```

### Configuration and Environment Variables

Configuration is managed in `~/.readpile/config.toml`. `readpile init` creates this file for you and interactively prompts for required secrets.

| Variable/Key | Location | Purpose |
|--------------|----------|---------|
| `api_key` | `[llm]` in `config.toml` | API key for your LLM provider (used by sync pipeline). Not needed for local models |
| `smtp_password` | `[sync.digest]` in `config.toml` | Gmail App Password for the **readpile inbox** — lets readpile send digest emails |
| `hf_token` | `[transcribe]` in `config.toml` | HuggingFace token for optional speaker diarization |
| `READPILE_CONFIG` | Environment variable | Override the default `~/.readpile/config.toml` path |
| `YOUTUBE_COOKIES` | Environment or `config.toml` | Path to YouTube cookie file (see below) |

### Gmail OAuth setup

readpile needs two things from your readpile Gmail account: an **App Password** (to send digest emails) and **OAuth credentials** (to read the inbox). The App Password is straightforward — the OAuth part requires a one-time Google Cloud setup. Here's the full walkthrough:

**1. Create a Google Cloud project**

1. Go to [console.cloud.google.com](https://console.cloud.google.com/) and sign in with any Google account (doesn't have to be the readpile inbox account)
2. Click the project dropdown at the top of the page → **New Project**
3. Name it something like "readpile" → **Create**
4. Make sure the new project is selected in the dropdown

**2. Enable the Gmail API**

1. In the left sidebar, go to **APIs & Services → Library**
2. Search for "Gmail API"
3. Click **Gmail API** → **Enable**

**3. Configure the OAuth consent screen**

1. Go to **APIs & Services → OAuth consent screen**
2. Select **External** (unless you have a Google Workspace org) → **Create**
3. Fill in the required fields:
   - App name: `readpile`
   - User support email: your email
   - Developer contact: your email
4. Click **Save and Continue** through the remaining steps (Scopes, Test users, Summary)
5. On the **Test users** step, click **Add Users** and add the readpile inbox email (e.g. `readpile-inbox@gmail.com`)

**4. Create OAuth client credentials**

1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → OAuth client ID**
3. Application type: **Desktop app**
4. Name: `readpile`
5. Click **Create**
6. Click **Download JSON** on the confirmation dialog
7. Move the downloaded file to `~/.readpile/email-credentials.json`:

```bash
mv ~/Downloads/client_secret_*.json ~/.readpile/email-credentials.json
chmod 600 ~/.readpile/email-credentials.json
```

**5. Authorize readpile**

Run `readpile sync` — it will open your browser and ask you to sign in with the readpile inbox account and grant access. This is a one-time step; the token is cached in `~/.readpile/email-token.json` and refreshes automatically after that.

```bash
readpile sync
# Browser opens → sign in with readpile-inbox@gmail.com → click Allow
```

> **Note:** Since the app is in "Testing" mode, Google shows a warning screen. Click **Advanced → Go to readpile (unsafe)**. This is safe — you created this app yourself. If you want to remove the warning, publish the app from the OAuth consent screen (no review needed for personal use with fewer than 100 users).

### YouTube IP blocks

YouTube blocks transcript requests from certain IPs (cloud, corporate, VPN). readpile falls back to `yt-dlp` with cookie authentication automatically. Export cookies once:

```bash
yt-dlp --cookies-from-browser chrome --cookies ~/.readpile/youtube-cookies.txt https://youtube.com
```

readpile checks: `~/.readpile/youtube-cookies.txt`, then `YOUTUBE_COOKIES` env var, then `youtube_cookies` in config. Re-export when cookies expire. Replace `chrome` with your browser: `firefox`, `safari`, `edge`, `chromium`, `opera`, `brave`.

---

## Terminology

| Term | Meaning |
|------|---------|
| **Source file** | Raw extracted content saved to `~/my-wiki/sources/`. Immutable — the LLM reads from these but never modifies them. Created by `wiki_save_source` or by the sync pipeline |
| **Wiki page** | LLM-synthesized page in `~/my-wiki/pages/`. Summaries, entity pages, comparisons, explorations. Created and updated by `wiki_write` |
| **Feed** | An RSS feed, YouTube channel, or podcast configured in `~/.readpile/feeds.toml` via `readpile feeds add`. The sync pipeline checks these for new content |
| **Digest** | The daily email sent by `readpile sync` with topic-grouped summaries of new content |

---

## Security

All secrets stay outside the codebase and outside git:

| Data | Storage | Protection |
|------|---------|------------|
| LLM API key | `~/.readpile/config.toml` | chmod 600, not in repo |
| SMTP password | `~/.readpile/config.toml` | chmod 600, not in repo |
| HuggingFace token | `~/.readpile/config.toml` | chmod 600, not in repo |
| OAuth client credentials | `~/.readpile/email-credentials.json` | chmod 600, not in repo |
| OAuth token | `~/.readpile/email-token.json` | chmod 600, auto-refreshed |
| Wiki content | `~/my-wiki/` | No secrets — safe for git or Obsidian |

`readpile init` creates `~/.readpile/` with chmod 700 and sets chmod 600 on the configuration and credential files automatically.

The sync pipeline is designed for a single machine. The state file (`~/.readpile/sync-state.json`) is machine-local. If you sync your wiki via git or cloud storage, only run `readpile sync` on one machine to avoid duplicate processing.

---

## License

MIT — see [LICENSE](LICENSE) for details. See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup.
