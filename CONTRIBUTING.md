# Contributing to readpile

## Development setup

```bash
git clone https://github.com/ankurawl/readpile.git
cd readpile
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,all]"
python -m playwright install chromium
```

### MCP server with a venv

The repo's `.mcp.json` uses `readpile-mcp`, which must be in PATH. When developing from source in a venv, Claude Code can't find the venv binary. Two workarounds:

1. Update `.mcp.json` locally: `{ "command": ".venv/bin/readpile-mcp" }`
2. Install globally alongside the venv: `pip install -e ".[mcp]"` (without the venv activated)

## Running tests

```bash
pytest tests/ -v                                           # full suite
pytest tests/ -m "not slow and not network and not audio"  # fast tests only
```

Test markers:
- `slow` — tests taking >5s (integration tests with real file I/O)
- `network` — tests requiring network access
- `audio` — tests requiring Whisper/audio dependencies

## Project structure

```
src/readpile/
├── cli/             # CLI entry points (main.py parent app, wiki.py, sync.py)
├── scrapers/        # Article + webpage content extraction
├── transcribers/    # YouTube captions + Whisper audio transcription
├── crawlers/        # RSS, blog, site, discovery (feed/podcast/YouTube resolution)
├── core/            # Config, models, archiver, URL detector, robots.txt
├── wiki/            # LLMWiki module (models.py, store.py)
├── sync/            # Sync pipeline (email, feeds, digest, synthesis, state)
│   └── email/       # Gmail OAuth provider + content extraction
└── mcp_server.py    # MCP server (FastMCP)
```

## Adding a new scraper or transcriber

1. Create a module in `src/readpile/scrapers/` or `src/readpile/transcribers/`
2. Return a `ContentItem` — the universal format (YAML front matter + markdown body)
3. Add a `_check_deps()` guard at module level for any optional dependencies
4. Wire it into `mcp_server.py` as a new MCP tool (thin wrapper around the function)
5. Add tests in `tests/`

## Key abstractions

**`ContentItem`** (`core/models.py`) — Every piece of extracted content is a `ContentItem` with a `to_yaml_header()` and `to_stdout()` method. All tools produce and consume this format.

**`WikiStore`** (`wiki/store.py`) — Single class for all wiki operations. Methods: `init()`, `read_page()`, `write_page()`, `save_source()`, `list_pages()`, `search()`, `append_log()`, `delete_page()`, `build_index()`.

**`Archiver`** (`core/archiver.py`) — Handles filename sanitization (`YYYY-MM-DD_title-slug.md`) and file writing. Used by both the `archive` command and `WikiStore.save_source()`.

## MCP tool conventions

MCP tools in `mcp_server.py` are thin wrappers — they validate inputs, call existing functions, and format the output as a string. They should:

- Catch `SystemExit` from `_check_deps()` guards and return the error as a string (don't kill the server)
- Use lazy imports inside the tool function for fast server startup
- Return plain strings, not objects
- Handle errors gracefully — return descriptive error messages, not stack traces
