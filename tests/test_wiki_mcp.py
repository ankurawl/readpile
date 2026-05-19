"""Tests for wiki MCP tools — integration tests via the MCP server."""

import tempfile
from datetime import date
from pathlib import Path

import pytest

from readpile.mcp_server import _create_server


def _get_tool(name):
    server = _create_server()
    return server._tool_manager._tools[name].fn


def _make_page(title="Test Page", category="concept", body="Test body."):
    return f"""---
title: "{title}"
category: {category}
ingested: 2026-05-17
updated: 2026-05-17
---

{body}
"""


class TestWikiInit:
    def test_creates_wiki(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki_init = _get_tool("wiki_init")
            result = wiki_init(path=f"{tmp}/wiki", name="Test Wiki")
            assert "Wiki created" in result
            assert "Conventions" in result
            assert "Ingest workflow" in result
            assert Path(f"{tmp}/wiki/.wiki.toml").exists()
            assert Path(f"{tmp}/wiki/wiki-conventions.md").exists()

    def test_duplicate_init_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki_init = _get_tool("wiki_init")
            wiki_init(path=f"{tmp}/wiki", name="Wiki")
            result = wiki_init(path=f"{tmp}/wiki", name="Wiki 2")
            assert "Error" in result


class TestWikiRoundTrip:
    def test_full_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki_path = f"{tmp}/wiki"
            wiki_init = _get_tool("wiki_init")
            wiki_init(path=wiki_path, name="RT Wiki")

            save_source = _get_tool("wiki_save_source")
            source_result = save_source(
                content="Article about transformers.",
                title="Transformers Article",
                source_url="https://example.com/transformers",
                date="2026-05-10",
                wiki_dir=wiki_path,
            )
            assert "sources" in source_result

            wiki_read = _get_tool("wiki_read")
            index = wiki_read(page="index", wiki_dir=wiki_path)
            assert "0 pages" in index

            wiki_write = _get_tool("wiki_write")
            page_content = _make_page(title="Transformers", body="Neural network architecture.")
            write_result = wiki_write(
                content=page_content,
                wiki_dir=wiki_path,
                page="transformers",
            )
            assert "Page written" in write_result
            assert "Index auto-rebuilt" in write_result

            page_text = wiki_read(page="transformers", wiki_dir=wiki_path)
            assert "Transformers" in page_text
            assert "Neural network" in page_text

            source_files = list(Path(wiki_path, "sources").glob("*.md"))
            assert len(source_files) == 1
            source_name = f"sources/{source_files[0].stem}"
            source_text = wiki_read(page=source_name, wiki_dir=wiki_path)
            assert "Article about transformers" in source_text

            wiki_list = _get_tool("wiki_list")
            list_result = wiki_list(wiki_dir=wiki_path)
            assert "transformers" in list_result
            assert "Transformers" in list_result

            wiki_search = _get_tool("wiki_search")
            search_result = wiki_search(query="neural", wiki_dir=wiki_path)
            assert "transformers" in search_result


class TestWikiWriteRebuildIndex:
    def test_rebuild_false_skips_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki_path = f"{tmp}/wiki"
            _get_tool("wiki_init")(path=wiki_path, name="Wiki")

            wiki_write = _get_tool("wiki_write")
            wiki_read = _get_tool("wiki_read")

            wiki_write(
                content=_make_page(title="First"),
                wiki_dir=wiki_path,
                page="first",
                rebuild_index=False,
            )
            index = wiki_read(page="index", wiki_dir=wiki_path)
            assert "0 pages" in index

            wiki_write(
                content=_make_page(title="Second"),
                wiki_dir=wiki_path,
                page="second",
                rebuild_index=True,
            )
            index = wiki_read(page="index", wiki_dir=wiki_path)
            assert "First" in index
            assert "Second" in index
            assert "2 pages" in index


class TestWikiDelete:
    def test_deletes_page_and_rebuilds(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki_path = f"{tmp}/wiki"
            _get_tool("wiki_init")(path=wiki_path, name="Wiki")

            wiki_write = _get_tool("wiki_write")
            wiki_write(
                content=_make_page(title="To Delete"),
                wiki_dir=wiki_path,
                page="to-delete",
            )
            assert Path(wiki_path, "pages", "to-delete.md").exists()

            wiki_delete = _get_tool("wiki_delete")
            result = wiki_delete(page="to-delete", wiki_dir=wiki_path)
            assert "Deleted" in result
            assert not Path(wiki_path, "pages", "to-delete.md").exists()

            index = _get_tool("wiki_read")(page="index", wiki_dir=wiki_path)
            assert "To Delete" not in index

    def test_rejects_reserved_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki_path = f"{tmp}/wiki"
            _get_tool("wiki_init")(path=wiki_path, name="Wiki")
            wiki_delete = _get_tool("wiki_delete")
            for name in ("log", "index", "conventions"):
                result = wiki_delete(page=name, wiki_dir=wiki_path)
                assert "Error" in result

    def test_missing_page_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki_path = f"{tmp}/wiki"
            _get_tool("wiki_init")(path=wiki_path, name="Wiki")
            result = _get_tool("wiki_delete")(page="nonexistent", wiki_dir=wiki_path)
            assert "Error" in result


class TestWikiLog:
    def test_appends_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki_path = f"{tmp}/wiki"
            _get_tool("wiki_init")(path=wiki_path, name="Wiki")

            wiki_log = _get_tool("wiki_log")
            result = wiki_log(
                entry='ingest | "Article" | https://example.com\n- Created page: article.md',
                wiki_dir=wiki_path,
            )
            assert "Logged" in result

            log_content = _get_tool("wiki_read")(page="log", wiki_dir=wiki_path)
            assert "ingest" in log_content
            assert "Wiki Log" in log_content

    def test_preserves_existing_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki_path = f"{tmp}/wiki"
            _get_tool("wiki_init")(path=wiki_path, name="Wiki")

            wiki_log = _get_tool("wiki_log")
            wiki_log(entry="first entry", wiki_dir=wiki_path)
            wiki_log(entry="second entry", wiki_dir=wiki_path)

            log = _get_tool("wiki_read")(page="log", wiki_dir=wiki_path)
            assert "first entry" in log
            assert "second entry" in log


class TestWikiWriteRejects:
    def test_rejects_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki_path = f"{tmp}/wiki"
            _get_tool("wiki_init")(path=wiki_path, name="Wiki")
            result = _get_tool("wiki_write")(
                content=_make_page(), wiki_dir=wiki_path, page="log",
            )
            assert "Error" in result

    def test_rejects_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki_path = f"{tmp}/wiki"
            _get_tool("wiki_init")(path=wiki_path, name="Wiki")
            result = _get_tool("wiki_write")(
                content=_make_page(), wiki_dir=wiki_path, page="index",
            )
            assert "Error" in result

    def test_rejects_conventions(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki_path = f"{tmp}/wiki"
            _get_tool("wiki_init")(path=wiki_path, name="Wiki")
            result = _get_tool("wiki_write")(
                content=_make_page(), wiki_dir=wiki_path, page="conventions",
            )
            assert "Error" in result


class TestWikiReadConventions:
    def test_returns_conventions(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki_path = f"{tmp}/wiki"
            _get_tool("wiki_init")(path=wiki_path, name="Wiki")
            result = _get_tool("wiki_read")(page="conventions", wiki_dir=wiki_path)
            assert "Wiki Conventions" in result
            assert "Ingest workflow" in result


class TestWikiReadLog:
    def test_returns_full_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki_path = f"{tmp}/wiki"
            _get_tool("wiki_init")(path=wiki_path, name="Wiki")
            _get_tool("wiki_log")(entry="test entry", wiki_dir=wiki_path)
            log = _get_tool("wiki_read")(page="log", wiki_dir=wiki_path)
            assert "test entry" in log


class TestResolveWikiDir:
    def test_explicit_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki_path = f"{tmp}/wiki"
            _get_tool("wiki_init")(path=wiki_path, name="Wiki")
            result = _get_tool("wiki_read")(page="index", wiki_dir=wiki_path)
            assert "Wiki Index" in result

    def test_missing_dir_error(self):
        result = _get_tool("wiki_read")(page="index", wiki_dir=None)
        assert "Error" in result

    def test_no_wiki_at_path_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _get_tool("wiki_read")(page="index", wiki_dir=tmp)
            assert "Error" in result
            assert "wiki_init" in result

    def test_config_fallback(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            wiki_path = f"{tmp}/wiki"
            _get_tool("wiki_init")(path=wiki_path, name="Wiki")

            config_file = Path(tmp) / "config.toml"
            config_file.write_text(f'[wiki]\ndefault_dir = "{wiki_path}"\n')
            monkeypatch.setenv("READPILE_CONFIG", str(config_file))

            result = _get_tool("wiki_read")(page="index", wiki_dir=None)
            assert "Wiki Index" in result


class TestToolDescriptionsMentionConventions:
    def test_wiki_save_source_mentions_conventions(self):
        server = _create_server()
        tool = server._tool_manager._tools["wiki_save_source"]
        desc = tool.fn.__doc__ or ""
        assert "conventions" in desc.lower()

    def test_wiki_write_mentions_conventions(self):
        server = _create_server()
        tool = server._tool_manager._tools["wiki_write"]
        desc = tool.fn.__doc__ or ""
        assert "conventions" in desc.lower()


class TestErrorCases:
    def test_invalid_page_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki_path = f"{tmp}/wiki"
            _get_tool("wiki_init")(path=wiki_path, name="Wiki")
            result = _get_tool("wiki_write")(
                content=_make_page(category="nonexistent"),
                wiki_dir=wiki_path,
                page="test",
            )
            assert "Error" in result
            assert "category" in result.lower()


class TestConfigDefaults:
    def test_wiki_section_in_defaults(self, monkeypatch, tmp_path):
        monkeypatch.setenv("READPILE_CONFIG", str(tmp_path / "nonexistent.toml"))
        from readpile.core.config import load_config
        config = load_config()
        assert "wiki" in config
        assert config["wiki"]["default_dir"] == "~/my-wiki"
