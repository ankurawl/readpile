"""Wiki store — all wiki operations in a single class."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path

from readpile.wiki.models import WikiConfig, WikiPage

CATEGORY_HEADINGS: dict[str, str] = {
    "concept": "Concepts",
    "entity": "Entities",
    "summary": "Summaries",
    "comparison": "Comparisons",
    "exploration": "Explorations",
    "reference": "References",
}

_DEFAULT_CONVENTIONS = """\
# Wiki Conventions

## Ingest workflow
When given a URL to add to the wiki, follow these steps:
1. Use `scrape` to get the content and extract metadata (title, author, publication date).
2. Use `wiki_save_source` to save the raw content to sources/.
3. Use `wiki_read("index")` to understand the current wiki state.
4. Read any existing pages related to the new content.
5. Decide what pages to create or update based on the rules below.
6. Use `wiki_write` for each new/updated page, with correct frontmatter:
   - `source_date`: original publication date of the source
   - `ingested`: today's date (never change on updates)
   - `updated`: today's date
   When writing multiple pages, pass `rebuild_index=false` on all but the last `wiki_write` call to avoid redundant index rebuilds. The last call (with `rebuild_index=true`, the default) rebuilds the index once.
7. Log the operation: call `wiki_log` with a summary of what was done (e.g., `ingest | Title | URL` followed by bullet points for pages created/updated). The tool handles the `## [date]` prefix and file append.

## Page creation rules
- Always create entity pages for people, organizations, and projects mentioned prominently.
- Always create or update concept pages for technical concepts explained in the source.
- For articles that compare things, create a comparison page.
- For articles that are primarily informational, create a summary page.
- When updating an existing page, preserve its `ingested` date — only change `updated`.

## Temporal awareness
- When synthesizing from sources with different dates, always note which claims come from which time period.
- Prefer newer sources over older ones when they conflict. Note the conflict and resolution.
- Flag any claim older than 12 months in a fast-moving field (AI, crypto, etc.) with a staleness note.
- Always populate `source_date` in frontmatter when the original publication date is known.

## Cross-referencing
- Add [[wikilinks]] to related pages whenever a concept is mentioned.
- If a wikilink target doesn't exist yet, still add the link — it marks a gap to fill later.

## Query workflow
When answering a question using the wiki:
1. Use `wiki_read("index")` to find relevant pages, then `wiki_search` as a fallback.
2. Read the relevant pages and synthesize an answer.
3. If the synthesized answer is substantive and reusable, file it back as a new wiki page.
   - Use category `exploration` for query-derived pages (not `summary` or `comparison`, which are reserved for pages synthesized from actual content sources).
   - Mark the `sources` frontmatter field as empty or reference the wiki pages consulted — these pages are derived from the wiki itself, not from external sources.
   - This makes explorations compound — future queries benefit from past ones.
4. Log the operation via `wiki_log`.

## Synthesis style
- Write for your future self: concise, scannable, with key takeaways up front.
- Comparisons should use tables when comparing more than two items.
- Summaries should be 3-5 paragraphs max, with a "Key Ideas" bullet list.
"""


def _sanitize_slug(title: str, max_length: int = 80) -> str:
    name = title.lower()
    name = re.sub(r"[^a-z0-9 \-]", "", name)
    name = re.sub(r"[\s_]+", "-", name)
    name = re.sub(r"-+", "-", name)
    name = name.strip("-")
    name = name[:max_length].rstrip("-")
    return name


def _validate_path(name: str, wiki_dir: Path) -> None:
    if ".." in name or name.startswith("/"):
        raise ValueError(f"Invalid page name: {name!r} — directory traversal is not allowed")


class WikiStore:
    """All wiki operations on a single directory."""

    def __init__(self, wiki_dir: str | Path) -> None:
        self.wiki_dir = Path(wiki_dir).expanduser().resolve()

    @property
    def pages_dir(self) -> Path:
        return self.wiki_dir / "pages"

    @property
    def sources_dir(self) -> Path:
        return self.wiki_dir / "sources"

    @property
    def index_path(self) -> Path:
        return self.wiki_dir / "index.md"

    @property
    def log_path(self) -> Path:
        return self.wiki_dir / "log.md"

    @property
    def config_path(self) -> Path:
        return self.wiki_dir / ".wiki.toml"

    @property
    def conventions_path(self) -> Path:
        return self.wiki_dir / "wiki-conventions.md"

    def exists(self) -> bool:
        return self.config_path.exists()

    def load_config(self) -> WikiConfig:
        text = self.config_path.read_text(encoding="utf-8")
        return WikiConfig.from_toml(text)

    def init(
        self,
        name: str,
        description: str = "",
        categories: list[str] | None = None,
    ) -> Path:
        if self.exists():
            raise FileExistsError(f"Wiki already exists at {self.wiki_dir}")

        self.wiki_dir.mkdir(parents=True, exist_ok=True)
        self.pages_dir.mkdir(exist_ok=True)
        self.sources_dir.mkdir(exist_ok=True)

        config = WikiConfig(
            name=name,
            description=description,
            categories=categories or WikiConfig.__dataclass_fields__["categories"].default_factory(),
        )
        self.config_path.write_text(config.to_toml(), encoding="utf-8")

        self._create_default_conventions()

        self.index_path.write_text(
            f"# {name} — Wiki Index\n\n"
            f"> 0 pages across 0 categories | Last updated: {date.today().isoformat()}\n",
            encoding="utf-8",
        )

        self.log_path.write_text("# Wiki Log\n", encoding="utf-8")

        return self.wiki_dir

    def _create_default_conventions(self) -> None:
        self.conventions_path.write_text(_DEFAULT_CONVENTIONS, encoding="utf-8")

    def load_conventions(self) -> str:
        if not self.conventions_path.exists():
            raise FileNotFoundError(f"Conventions file not found: {self.conventions_path}")
        return self.conventions_path.read_text(encoding="utf-8")

    def read_page(self, name: str) -> str:
        if name == "index":
            return self.index_path.read_text(encoding="utf-8")
        if name == "log":
            return self.log_path.read_text(encoding="utf-8")
        if name == "conventions":
            return self.load_conventions()

        if name.startswith("sources/"):
            _validate_path(name, self.wiki_dir)
            source_name = name[len("sources/"):]
            if not source_name.endswith(".md"):
                source_name += ".md"
            source_path = self.sources_dir / source_name
            resolved = source_path.resolve()
            if not str(resolved).startswith(str(self.wiki_dir)):
                raise ValueError(f"Invalid source path: {name!r}")
            if not source_path.exists():
                raise FileNotFoundError(f"Source not found: {name}")
            return source_path.read_text(encoding="utf-8")

        _validate_path(name, self.wiki_dir)
        if not name.endswith(".md"):
            name += ".md"
        page_path = self.pages_dir / name
        resolved = page_path.resolve()
        if not str(resolved).startswith(str(self.wiki_dir)):
            raise ValueError(f"Invalid page name: {name!r}")
        if not page_path.exists():
            raise FileNotFoundError(f"Page not found: {name}")
        return page_path.read_text(encoding="utf-8")

    def write_page(
        self,
        name: str | None,
        content: str,
        rebuild_index: bool = True,
    ) -> Path:
        page = WikiPage.from_markdown(content)

        config = self.load_config()
        if page.category not in config.categories:
            valid = ", ".join(config.categories)
            raise ValueError(
                f"Invalid category '{page.category}'. Valid categories: {valid}"
            )

        if name is None:
            name = _sanitize_slug(page.title)

        reserved = {"log", "index", "conventions"}
        clean_name = name.removesuffix(".md")
        if clean_name in reserved:
            if clean_name == "log":
                raise ValueError("Cannot write 'log' — use wiki_log / append_log() instead")
            elif clean_name == "index":
                raise ValueError("Cannot write 'index' — it is auto-managed")
            else:
                raise ValueError("Cannot write 'conventions' — edit wiki-conventions.md directly")

        _validate_path(name, self.wiki_dir)
        if not name.endswith(".md"):
            name += ".md"

        page_path = self.pages_dir / name
        resolved = page_path.resolve()
        if not str(resolved).startswith(str(self.wiki_dir)):
            raise ValueError(f"Invalid page name: {name!r}")

        self.pages_dir.mkdir(exist_ok=True)
        page_path.write_text(content, encoding="utf-8")

        if rebuild_index:
            index_content = self.build_index()
            self.index_path.write_text(index_content, encoding="utf-8")

        return page_path

    def delete_page(self, name: str) -> None:
        reserved = {"log", "index", "conventions"}
        clean_name = name.removesuffix(".md")
        if clean_name in reserved:
            if clean_name == "log":
                raise ValueError("Cannot delete 'log' — it is append-only")
            elif clean_name == "index":
                raise ValueError("Cannot delete 'index' — it is auto-managed")
            else:
                raise ValueError("Cannot delete 'conventions' — edit wiki-conventions.md directly")

        _validate_path(name, self.wiki_dir)
        if not name.endswith(".md"):
            name += ".md"

        page_path = self.pages_dir / name
        resolved = page_path.resolve()
        if not str(resolved).startswith(str(self.wiki_dir)):
            raise ValueError(f"Invalid page name: {name!r}")

        if not page_path.exists():
            raise FileNotFoundError(f"Page not found: {name}")

        page_path.unlink()
        index_content = self.build_index()
        self.index_path.write_text(index_content, encoding="utf-8")

    def save_source(
        self,
        content: str,
        title: str,
        source_url: str,
        content_type: str = "article",
        date: str | None = None,
        author: str | None = None,
    ) -> Path:
        from readpile.core.models import ContentItem, ContentType
        from readpile.core.archiver import Archiver

        ct = ContentType(content_type)

        date_val = None
        if date is not None:
            from datetime import date as date_type
            date_val = date_type.fromisoformat(date)

        item = ContentItem(
            text=content,
            title=title,
            source_url=source_url,
            content_type=ct,
            date=date_val,
            author=author,
        )

        archiver = Archiver(self.sources_dir)
        return archiver.save(item)

    def list_pages(self, category: str | None = None) -> list[dict]:
        if not self.pages_dir.exists():
            return []

        pages: list[dict] = []
        for path in sorted(self.pages_dir.glob("*.md")):
            try:
                text = path.read_text(encoding="utf-8")
                page = WikiPage.from_markdown(text)
                entry = {
                    "name": path.stem,
                    "title": page.title,
                    "category": page.category,
                    "tags": page.tags,
                    "source_date": page.source_date,
                    "ingested": page.ingested,
                    "updated": page.updated,
                }
                if category is None or page.category == category:
                    pages.append(entry)
            except (ValueError, KeyError):
                continue

        pages.sort(key=lambda p: p["title"].lower())
        return pages

    def build_index(self) -> str:
        pages = self.list_pages()
        config = self.load_config()

        by_category: dict[str, list[dict]] = {}
        for p in pages:
            by_category.setdefault(p["category"], []).append(p)

        total = len(pages)
        cat_count = len(by_category)
        today = date.today().isoformat()

        lines = [
            f"# {config.name} — Wiki Index",
            "",
            f"> {total} pages across {cat_count} categories | Last updated: {today}",
        ]

        for cat in config.categories:
            if cat not in by_category:
                continue
            heading = CATEGORY_HEADINGS.get(cat, cat.title() + "s")
            lines.append("")
            lines.append(f"## {heading}")
            lines.append("")
            for p in by_category[cat]:
                lines.append(f"- [{p['title']}](pages/{p['name']}.md) [{p['category']}]")

        for cat in sorted(by_category.keys()):
            if cat in config.categories:
                continue
            heading = CATEGORY_HEADINGS.get(cat, cat.title() + "s")
            lines.append("")
            lines.append(f"## {heading}")
            lines.append("")
            for p in by_category[cat]:
                lines.append(f"- [{p['title']}](pages/{p['name']}.md) [{p['category']}]")

        lines.append("")
        return "\n".join(lines)

    def search(self, query: str, scope: str = "pages") -> list[dict]:
        results: list[dict] = []
        total_matches = 0
        query_lower = query.lower()

        dirs: list[tuple[Path, str]] = []
        if scope in ("pages", "all"):
            dirs.append((self.pages_dir, "page"))
        if scope in ("sources", "all"):
            dirs.append((self.sources_dir, "source"))

        for search_dir, kind in dirs:
            if not search_dir.exists():
                continue
            for path in sorted(search_dir.glob("*.md")):
                if total_matches >= 50:
                    break

                text = path.read_text(encoding="utf-8")
                lines = text.splitlines()

                title = path.stem
                tags_str = ""
                try:
                    page = WikiPage.from_markdown(text)
                    title = page.title
                    tags_str = " ".join(page.tags)
                except (ValueError, KeyError):
                    pass

                file_matches: list[dict] = []
                for i, line in enumerate(lines):
                    if query_lower in line.lower():
                        start = max(0, i - 2)
                        end = min(len(lines), i + 3)
                        context = "\n".join(lines[start:end])
                        file_matches.append({
                            "line_number": i + 1,
                            "context": context,
                        })
                        if len(file_matches) >= 20:
                            break

                if not file_matches and query_lower in title.lower():
                    file_matches.append({
                        "line_number": 0,
                        "context": f"Title match: {title}",
                    })

                if not file_matches and query_lower in tags_str.lower():
                    file_matches.append({
                        "line_number": 0,
                        "context": f"Tag match: {tags_str}",
                    })

                if file_matches:
                    prefix = "sources/" if kind == "source" else ""
                    results.append({
                        "name": f"{prefix}{path.stem}",
                        "title": title,
                        "matches": file_matches,
                    })
                    total_matches += len(file_matches)

        return results

    def append_log(self, entry: str) -> None:
        today = date.today().isoformat()
        log_entry = f"\n## [{today}] {entry}\n"
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(log_entry)

    def read_log(self, recent: int | None = None) -> str:
        text = self.log_path.read_text(encoding="utf-8")
        if recent is None:
            return text

        sections = re.split(r"(?=\n## \[)", text)
        header = sections[0] if sections else ""
        entries = [s for s in sections[1:] if s.strip()]
        recent_entries = entries[-recent:] if recent <= len(entries) else entries
        return header + "".join(recent_entries)
