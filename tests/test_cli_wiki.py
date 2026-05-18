"""Tests for wiki CLI commands."""

import tempfile

from typer.testing import CliRunner

from readpile.cli.wiki import app

runner = CliRunner()


class TestWikiInit:
    def test_creates_wiki(self, tmp_path):
        wiki_path = str(tmp_path / "wiki")
        result = runner.invoke(app, ["init", wiki_path, "--name", "Test Wiki"])
        assert result.exit_code == 0
        assert "Wiki created" in result.output
        assert (tmp_path / "wiki" / ".wiki.toml").exists()
        assert (tmp_path / "wiki" / "wiki-conventions.md").exists()
        assert (tmp_path / "wiki" / "index.md").exists()
        assert (tmp_path / "wiki" / "log.md").exists()
        assert (tmp_path / "wiki" / "pages").exists()
        assert (tmp_path / "wiki" / "sources").exists()


class TestWikiList:
    def test_empty_wiki(self, tmp_path):
        wiki_path = str(tmp_path / "wiki")
        runner.invoke(app, ["init", wiki_path, "--name", "Wiki"])
        result = runner.invoke(app, ["list", "--wiki", wiki_path])
        assert result.exit_code == 0
        assert "No pages" in result.output

    def test_lists_pages(self, tmp_path):
        from readpile.wiki import WikiStore
        wiki_path = tmp_path / "wiki"
        store = WikiStore(wiki_path)
        store.init("Wiki")
        store.write_page("test", """---
title: Test Page
category: concept
ingested: 2026-05-17
updated: 2026-05-17
---

Body.
""")
        result = runner.invoke(app, ["list", "--wiki", str(wiki_path)])
        assert result.exit_code == 0
        assert "Test Page" in result.output
        assert "concept" in result.output

    def test_filters_by_category(self, tmp_path):
        from readpile.wiki import WikiStore
        wiki_path = tmp_path / "wiki"
        store = WikiStore(wiki_path)
        store.init("Wiki")
        store.write_page("c", """---
title: Concept
category: concept
ingested: 2026-05-17
updated: 2026-05-17
---

Body.
""", rebuild_index=False)
        store.write_page("e", """---
title: Entity
category: entity
ingested: 2026-05-17
updated: 2026-05-17
---

Body.
""")
        result = runner.invoke(app, ["list", "--wiki", str(wiki_path), "--category", "concept"])
        assert result.exit_code == 0
        assert "Concept" in result.output
        assert "Entity" not in result.output


class TestWikiSearch:
    def test_finds_match(self, tmp_path):
        from readpile.wiki import WikiStore
        wiki_path = tmp_path / "wiki"
        store = WikiStore(wiki_path)
        store.init("Wiki")
        store.write_page("test", """---
title: Searchable
category: concept
ingested: 2026-05-17
updated: 2026-05-17
---

Unique content findme123.
""")
        result = runner.invoke(app, ["search", "findme123", "--wiki", str(wiki_path)])
        assert result.exit_code == 0
        assert "Searchable" in result.output

    def test_no_results(self, tmp_path):
        from readpile.wiki import WikiStore
        wiki_path = tmp_path / "wiki"
        store = WikiStore(wiki_path)
        store.init("Wiki")
        result = runner.invoke(app, ["search", "nonexistent", "--wiki", str(wiki_path)])
        assert result.exit_code == 0
        assert "No results" in result.output

    def test_scope_all(self, tmp_path):
        from readpile.wiki import WikiStore
        wiki_path = tmp_path / "wiki"
        store = WikiStore(wiki_path)
        store.init("Wiki")
        store.save_source("findme source", "Source", "https://example.com")
        result = runner.invoke(app, ["search", "findme", "--wiki", str(wiki_path), "--scope", "all"])
        assert result.exit_code == 0
        assert "findme" in result.output


class TestWikiLog:
    def test_prints_log(self, tmp_path):
        from readpile.wiki import WikiStore
        wiki_path = tmp_path / "wiki"
        store = WikiStore(wiki_path)
        store.init("Wiki")
        store.append_log("test entry here")
        result = runner.invoke(app, ["log", "--wiki", str(wiki_path)])
        assert result.exit_code == 0
        assert "test entry here" in result.output

    def test_recent_filter(self, tmp_path):
        from readpile.wiki import WikiStore
        wiki_path = tmp_path / "wiki"
        store = WikiStore(wiki_path)
        store.init("Wiki")
        store.append_log("old entry")
        store.append_log("new entry")
        result = runner.invoke(app, ["log", "--wiki", str(wiki_path), "--recent", "1"])
        assert result.exit_code == 0
        assert "new entry" in result.output
        assert "old entry" not in result.output


class TestErrorCases:
    def test_missing_wiki_no_config(self):
        result = runner.invoke(app, ["list"])
        assert result.exit_code != 0 or "Error" in result.output

    def test_invalid_path(self, tmp_path):
        result = runner.invoke(app, ["list", "--wiki", str(tmp_path / "nonexistent")])
        assert result.exit_code != 0 or "Error" in result.output
