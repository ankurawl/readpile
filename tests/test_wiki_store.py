"""Tests for readpile.wiki.store — WikiStore class and all methods."""

from datetime import date
from pathlib import Path

import pytest

from readpile.wiki.store import WikiStore


def _make_page(title="Test Page", category="concept", body="Test body."):
    return f"""---
title: "{title}"
category: {category}
ingested: 2026-05-17
updated: 2026-05-17
---

{body}
"""


class TestInit:
    def test_creates_structure(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Test Wiki", "A test")
        assert store.config_path.exists()
        assert store.pages_dir.exists()
        assert store.sources_dir.exists()
        assert store.index_path.exists()
        assert store.log_path.exists()
        assert store.conventions_path.exists()

    def test_writes_config(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("My Wiki", "Description here")
        config = store.load_config()
        assert config.name == "My Wiki"
        assert config.description == "Description here"
        assert "concept" in config.categories

    def test_writes_conventions(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        conventions = store.load_conventions()
        assert "Ingest workflow" in conventions
        assert "Page creation rules" in conventions
        assert "Temporal awareness" in conventions
        assert "Cross-referencing" in conventions
        assert "Query workflow" in conventions
        assert "Synthesis style" in conventions
        assert "exploration" in conventions

    def test_writes_empty_index_and_log(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        index = store.read_page("index")
        assert "Wiki — Wiki Index" in index
        assert "0 pages" in index
        log = store.read_page("log")
        assert "Wiki Log" in log

    def test_raises_on_reinit(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        with pytest.raises(FileExistsError):
            store.init("Wiki Again")

    def test_custom_categories(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki", categories=["note", "recipe"])
        config = store.load_config()
        assert config.categories == ["note", "recipe"]


class TestReadPage:
    def test_reads_existing_page(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        content = _make_page()
        store.write_page("test-page", content)
        result = store.read_page("test-page")
        assert "Test Page" in result

    def test_reads_index(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        result = store.read_page("index")
        assert "Wiki Index" in result

    def test_reads_log(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        result = store.read_page("log")
        assert "Wiki Log" in result

    def test_reads_conventions(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        result = store.read_page("conventions")
        assert "Wiki Conventions" in result

    def test_reads_source(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        store.save_source("Content here", "Article", "https://example.com")
        sources = list(store.sources_dir.glob("*.md"))
        assert len(sources) == 1
        source_name = sources[0].stem
        result = store.read_page(f"sources/{source_name}")
        assert "Content here" in result

    def test_reads_source_with_md_extension(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        store.save_source("Content", "Art", "https://example.com")
        sources = list(store.sources_dir.glob("*.md"))
        source_name = sources[0].stem
        result = store.read_page(f"sources/{source_name}.md")
        assert "Content" in result

    def test_reads_page_with_md_extension(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        store.write_page("my-page", _make_page())
        result = store.read_page("my-page.md")
        assert "Test Page" in result

    def test_raises_on_missing_page(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        with pytest.raises(FileNotFoundError):
            store.read_page("nonexistent")

    def test_raises_on_missing_source(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        with pytest.raises(FileNotFoundError):
            store.read_page("sources/nonexistent")

    def test_rejects_directory_traversal(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        with pytest.raises(ValueError, match="traversal"):
            store.read_page("../../../etc/passwd")

    def test_rejects_absolute_path(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        with pytest.raises(ValueError, match="traversal"):
            store.read_page("/etc/passwd")

    def test_accepts_absolute_path_inside_wiki(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        
        # Test absolute path to a page
        store.write_page("my-page", _make_page(title="Absolute Test"))
        abs_page_path = (store.pages_dir / "my-page.md").resolve()
        result = store.read_page(str(abs_page_path))
        assert "Absolute Test" in result
        
        # Test absolute path to a source
        source_path = store.sources_dir / "raw.md"
        source_path.write_text("raw source content")
        result = store.read_page(str(source_path.resolve()))
        assert "raw source content" in result


class TestWritePage:
    def test_writes_valid_page(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        path = store.write_page("test", _make_page())
        assert path.exists()
        assert path.name == "test.md"

    def test_rejects_missing_frontmatter(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        with pytest.raises(ValueError):
            store.write_page("test", "No frontmatter here")

    def test_rejects_invalid_category(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        with pytest.raises(ValueError, match="category"):
            store.write_page("test", _make_page(category="invalid"))

    def test_auto_generates_filename(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        path = store.write_page(None, _make_page(title="My Cool Page"))
        assert path.name == "my-cool-page.md"

    def test_rejects_log(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        with pytest.raises(ValueError, match="log"):
            store.write_page("log", _make_page())

    def test_rejects_index(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        with pytest.raises(ValueError, match="index"):
            store.write_page("index", _make_page())

    def test_rejects_conventions(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        with pytest.raises(ValueError, match="conventions"):
            store.write_page("conventions", _make_page())

    def test_rejects_directory_traversal(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        with pytest.raises(ValueError, match="traversal"):
            store.write_page("../../evil", _make_page())

    def test_accepts_absolute_path_inside_wiki(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        abs_path = (store.pages_dir / "abs-write.md").resolve()
        path = store.write_page(str(abs_path), _make_page(title="Abs Write"))
        assert path.exists()
        assert path.name == "abs-write.md"
        assert "Abs Write" in path.read_text()

    def test_auto_rebuilds_index(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        store.write_page("test", _make_page(title="Test Page"))
        index = store.read_page("index")
        assert "Test Page" in index
        assert "1 pages" in index

    def test_rebuild_index_false_skips(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        store.write_page("test", _make_page(title="Test Page"), rebuild_index=False)
        index = store.read_page("index")
        assert "0 pages" in index
        idx = store.build_index()
        assert "Test Page" in idx

    def test_batch_write_pattern(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        store.write_page("p1", _make_page(title="Page One"), rebuild_index=False)
        store.write_page("p2", _make_page(title="Page Two"), rebuild_index=False)
        store.write_page("p3", _make_page(title="Page Three"), rebuild_index=False)
        store.write_page("p4", _make_page(title="Page Four"), rebuild_index=True)
        index = store.read_page("index")
        assert "Page One" in index
        assert "Page Two" in index
        assert "Page Three" in index
        assert "Page Four" in index
        assert "4 pages" in index


class TestDeletePage:
    def test_deletes_and_rebuilds_index(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        store.write_page("test", _make_page(title="Test"))
        assert "Test" in store.read_page("index")
        store.delete_page("test")
        assert not (store.pages_dir / "test.md").exists()
        assert "Test" not in store.read_page("index")
        assert "0 pages" in store.read_page("index")

    def test_raises_on_missing(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        with pytest.raises(FileNotFoundError):
            store.delete_page("nonexistent")

    def test_rejects_reserved_names(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        for name in ("log", "index", "conventions"):
            with pytest.raises(ValueError):
                store.delete_page(name)

    def test_rejects_directory_traversal(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        with pytest.raises(ValueError, match="traversal"):
            store.delete_page("../../evil")

    def test_accepts_absolute_path_inside_wiki(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        store.write_page("to-delete", _make_page())
        abs_path = (store.pages_dir / "to-delete.md").resolve()
        store.delete_page(str(abs_path))
        assert not abs_path.exists()


class TestSaveSource:
    def test_saves_to_sources_dir(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        path = store.save_source(
            "Article content",
            "Test Article",
            "https://example.com/article",
        )
        assert path.exists()
        assert str(path).startswith(str(store.sources_dir))
        assert "Article content" in path.read_text()

    def test_reuses_archiver(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        path = store.save_source(
            "Content", "Title", "https://example.com",
            content_type="youtube", date="2026-05-17", author="Author",
        )
        assert path.exists()
        content = path.read_text()
        assert "youtube" in content


class TestListPages:
    def test_lists_all(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        store.write_page("p1", _make_page(title="Alpha", category="concept"), rebuild_index=False)
        store.write_page("p2", _make_page(title="Beta", category="entity"), rebuild_index=False)
        pages = store.list_pages()
        assert len(pages) == 2
        assert pages[0]["title"] == "Alpha"
        assert pages[1]["title"] == "Beta"

    def test_filters_by_category(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        store.write_page("p1", _make_page(title="A", category="concept"), rebuild_index=False)
        store.write_page("p2", _make_page(title="B", category="entity"), rebuild_index=False)
        concepts = store.list_pages(category="concept")
        assert len(concepts) == 1
        assert concepts[0]["category"] == "concept"

    def test_returns_metadata(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        store.write_page("p1", _make_page(), rebuild_index=False)
        pages = store.list_pages()
        assert len(pages) == 1
        p = pages[0]
        assert "name" in p
        assert "title" in p
        assert "category" in p
        assert "tags" in p
        assert "source_date" in p
        assert "ingested" in p
        assert "updated" in p

    def test_empty_wiki(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        assert store.list_pages() == []


class TestBuildIndex:
    def test_generates_correct_headings(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        store.write_page("c1", _make_page(title="Concept A", category="concept"), rebuild_index=False)
        store.write_page("e1", _make_page(title="Entity B", category="entity"), rebuild_index=False)
        index = store.build_index()
        assert "## Concepts" in index
        assert "## Entities" in index
        assert "Concept A" in index
        assert "Entity B" in index

    def test_empty_wiki(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        index = store.build_index()
        assert "0 pages" in index
        assert "0 categories" in index

    def test_single_category(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        store.write_page("p1", _make_page(title="Only One"), rebuild_index=False)
        index = store.build_index()
        assert "1 pages" in index
        assert "1 categories" in index

    def test_includes_count_and_date(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        store.write_page("p1", _make_page(), rebuild_index=False)
        store.write_page("p2", _make_page(title="Two"), rebuild_index=False)
        index = store.build_index()
        assert "2 pages" in index
        assert date.today().isoformat() in index

    def test_alphabetical_sort(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        store.write_page("z", _make_page(title="Zebra"), rebuild_index=False)
        store.write_page("a", _make_page(title="Apple"), rebuild_index=False)
        index = store.build_index()
        apple_pos = index.index("Apple")
        zebra_pos = index.index("Zebra")
        assert apple_pos < zebra_pos

    def test_entry_format(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        store.write_page("my-page", _make_page(title="My Page"), rebuild_index=False)
        index = store.build_index()
        assert "- [My Page](pages/my-page.md) [concept]" in index


class TestAppendLog:
    def test_appends_with_date(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        store.append_log('ingest | "Test Article" | https://example.com')
        log = store.read_page("log")
        assert f"## [{date.today().isoformat()}]" in log
        assert "ingest" in log
        assert "Test Article" in log

    def test_append_only(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        store.append_log("first entry")
        store.append_log("second entry")
        log = store.read_page("log")
        assert "first entry" in log
        assert "second entry" in log
        assert log.index("first entry") < log.index("second entry")


class TestReadLog:
    def test_reads_full_log(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        store.append_log("entry one")
        store.append_log("entry two")
        log = store.read_log()
        assert "entry one" in log
        assert "entry two" in log

    def test_reads_recent_entries(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        store.append_log("old entry")
        store.append_log("new entry")
        recent = store.read_log(recent=1)
        assert "new entry" in recent
        assert "old entry" not in recent


class TestLoadConventions:
    def test_reads_conventions(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        content = store.load_conventions()
        assert "Wiki Conventions" in content

    def test_raises_if_missing(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        with pytest.raises(FileNotFoundError):
            store.load_conventions()


class TestSearch:
    def test_finds_in_body(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        store.write_page("p1", _make_page(title="Attention", body="Self-attention mechanism."))
        results = store.search("attention")
        assert len(results) >= 1
        assert results[0]["title"] == "Attention"

    def test_finds_in_tags(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        content = """---
title: Tagged Page
category: concept
tags: [unique-tag-xyz]
ingested: 2026-05-17
updated: 2026-05-17
---

No mention of the tag in body.
"""
        store.write_page("tagged", content)
        results = store.search("unique-tag-xyz")
        assert len(results) >= 1

    def test_scope_pages_only(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        store.write_page("p1", _make_page(title="Page Match", body="findme"))
        store.save_source("findme content", "Source Match", "https://example.com")
        results = store.search("findme", scope="pages")
        names = [r["name"] for r in results]
        assert any("p1" in n for n in names)
        assert not any("sources/" in n for n in names)

    def test_scope_sources_only(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        store.write_page("p1", _make_page(title="Page", body="findme"))
        store.save_source("findme content", "Source", "https://example.com")
        results = store.search("findme", scope="sources")
        names = [r["name"] for r in results]
        assert any("sources/" in n for n in names)
        assert not any(n == "p1" for n in names)

    def test_scope_all(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        store.write_page("p1", _make_page(title="Page", body="findme"))
        store.save_source("findme content", "Source", "https://example.com")
        results = store.search("findme", scope="all")
        assert len(results) >= 2

    def test_case_insensitive(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        store.write_page("p1", _make_page(title="Case Test", body="UPPERCASE content"))
        results = store.search("uppercase")
        assert len(results) >= 1

    def test_returns_context(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        store.write_page("p1", _make_page(title="Context", body="Line before\nTarget line\nLine after"))
        results = store.search("Target")
        assert len(results) >= 1
        assert any("context" in m for m in results[0]["matches"][0])

    def test_no_results(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        results = store.search("nonexistent-term-xyz")
        assert results == []

    def test_caps_results(self, tmp_path):
        store = WikiStore(tmp_path / "wiki")
        store.init("Wiki")
        for i in range(60):
            store.write_page(f"p{i}", _make_page(title=f"Page {i}", body="common"), rebuild_index=False)
        results = store.search("common")
        total = sum(len(r["matches"]) for r in results)
        assert total <= 50
