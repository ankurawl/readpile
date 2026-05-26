"""Tests for administrative CLI commands (wiki reading, point and mass deletions)."""

import os
from pathlib import Path
from typer.testing import CliRunner
from readpile.cli.main import app

runner = CliRunner()

def setup_wiki(tmp_path):
    wiki_path = tmp_path / "wiki"
    from readpile.wiki import WikiStore
    store = WikiStore(wiki_path)
    store.init("Test Wiki")
    return wiki_path, store

class TestWikiReadAndIndices:
    def test_list_is_enumerated(self, tmp_path):
        wiki_path, store = setup_wiki(tmp_path)
        store.write_page("page-a", "---\ntitle: Apple\ncategory: concept\ningested: 2026-05-17\nupdated: 2026-05-17\n---")
        store.write_page("page-b", "---\ntitle: Banana\ncategory: concept\ningested: 2026-05-17\nupdated: 2026-05-17\n---")
        
        result = runner.invoke(app, ["wiki", "list", "--wiki", str(wiki_path)])
        assert result.exit_code == 0
        assert "1. page-a — Apple" in result.output
        assert "2. page-b — Banana" in result.output

    def test_read_by_name(self, tmp_path):
        wiki_path, store = setup_wiki(tmp_path)
        content = "---\ntitle: Page\ncategory: concept\ningested: 2026-05-17\nupdated: 2026-05-17\n---\nHello World"
        store.write_page("test-page", content)
        
        result = runner.invoke(app, ["wiki", "read", "test-page", "--wiki", str(wiki_path)])
        assert result.exit_code == 0
        assert "Hello World" in result.output

    def test_read_by_index(self, tmp_path):
        wiki_path, store = setup_wiki(tmp_path)
        store.write_page("aaa", "---\ntitle: First\ncategory: concept\ningested: 2026-05-17\nupdated: 2026-05-17\n---\nContent A")
        store.write_page("bbb", "---\ntitle: Second\ncategory: concept\ningested: 2026-05-17\nupdated: 2026-05-17\n---\nContent B")
        
        result = runner.invoke(app, ["wiki", "read", "1", "--wiki", str(wiki_path)])
        assert result.exit_code == 0
        assert "Content A" in result.output
        
        result = runner.invoke(app, ["wiki", "read", "2", "--wiki", str(wiki_path)])
        assert result.exit_code == 0
        assert "Content B" in result.output

class TestWikiPointDeletions:
    def test_rm_page_by_name(self, tmp_path):
        wiki_path, store = setup_wiki(tmp_path)
        store.write_page("to-delete", "---\ntitle: Delete Me\ncategory: concept\ningested: 2026-05-17\nupdated: 2026-05-17\n---")
        assert (wiki_path / "pages" / "to-delete.md").exists()
        
        result = runner.invoke(app, ["wiki", "rm", "to-delete", "--wiki", str(wiki_path), "--force"])
        assert result.exit_code == 0
        assert not (wiki_path / "pages" / "to-delete.md").exists()

    def test_rm_page_by_index(self, tmp_path):
        wiki_path, store = setup_wiki(tmp_path)
        store.write_page("a", "---\ntitle: A\ncategory: concept\ningested: 2026-05-17\nupdated: 2026-05-17\n---")
        store.write_page("b", "---\ntitle: B\ncategory: concept\ningested: 2026-05-17\nupdated: 2026-05-17\n---")
        
        # 'a' is 1, 'b' is 2
        result = runner.invoke(app, ["wiki", "rm", "2", "--wiki", str(wiki_path), "--force"])
        assert result.exit_code == 0
        assert (wiki_path / "pages" / "a.md").exists()
        assert not (wiki_path / "pages" / "b.md").exists()

    def test_sources_and_rm_source(self, tmp_path):
        wiki_path, store = setup_wiki(tmp_path)
        store.save_source("content", "Source Title", "https://example.com")
        
        sources = store.list_sources()
        assert len(sources) == 1
        source_name = sources[0]["name"]
        
        # List sources
        result = runner.invoke(app, ["wiki", "sources", "--wiki", str(wiki_path)])
        assert result.exit_code == 0
        assert source_name in result.output
        
        # Remove source by index
        result = runner.invoke(app, ["wiki", "rm-source", "1", "--wiki", str(wiki_path), "--force"])
        assert result.exit_code == 0
        assert len(store.list_sources()) == 0

class TestCleanCommands:
    def test_clean_pages(self, tmp_path):
        wiki_path, store = setup_wiki(tmp_path)
        store.write_page("p1", "---\ntitle: P1\ncategory: concept\ningested: 2026-05-17\nupdated: 2026-05-17\n---")
        assert len(list(store.pages_dir.glob("*.md"))) == 1
        
        result = runner.invoke(app, ["clean", "pages", "--wiki", str(wiki_path), "--force"])
        assert result.exit_code == 0
        assert len(list(store.pages_dir.glob("*.md"))) == 0

    def test_clean_sources(self, tmp_path):
        wiki_path, store = setup_wiki(tmp_path)
        store.save_source("c", "S", "u")
        assert len(list(store.sources_dir.glob("*.md"))) == 1
        
        result = runner.invoke(app, ["clean", "sources", "--wiki", str(wiki_path), "--force"])
        assert result.exit_code == 0
        assert len(list(store.sources_dir.glob("*.md"))) == 0

    def test_clean_feeds(self, tmp_path, monkeypatch):
        # Setup mock config dir
        config_dir = tmp_path / ".readpile"
        config_dir.mkdir(exist_ok=True)
        feeds_toml = config_dir / "feeds.toml"
        feeds_toml.write_text("initial content")
        
        monkeypatch.setenv("READPILE_CONFIG", str(config_dir / "config.toml"))
        
        result = runner.invoke(app, ["clean", "feeds", "--force"])
        assert result.exit_code == 0
        assert feeds_toml.read_text() == ""

    def test_clean_configs(self, tmp_path, monkeypatch):
        config_dir = tmp_path / ".readpile"
        config_dir.mkdir(exist_ok=True)
        (config_dir / "config.toml").write_text("")
        
        monkeypatch.setenv("READPILE_CONFIG", str(config_dir / "config.toml"))
        
        result = runner.invoke(app, ["clean", "configs", "--force"])
        assert result.exit_code == 0
        assert not config_dir.exists()

    def test_clean_pages_resets_state(self, tmp_path, monkeypatch):
        wiki_path, store = setup_wiki(tmp_path)
        store.write_page("p1", "---\ntitle: P1\ncategory: concept\ningested: 2026-05-17\nupdated: 2026-05-17\n---")
        
        config_dir = tmp_path / ".readpile"
        config_dir.mkdir(exist_ok=True)
        state_file = config_dir / "sync-state.json"
        
        from readpile.sync.state import SyncState
        state = SyncState(state_file)
        state.mark_synthesized("p1")
        state.commit()
        
        monkeypatch.setenv("READPILE_CONFIG", str(config_dir / "config.toml"))
        (config_dir / "config.toml").write_text(f'[sync]\nstate_file = "{state_file}"')
        
        result = runner.invoke(app, ["clean", "pages", "--wiki", str(wiki_path), "--force"])
        assert result.exit_code == 0
        
        state.load()
        assert len(state.get_synthesized()) == 0

    def test_clean_sources_resets_state(self, tmp_path, monkeypatch):
        wiki_path, store = setup_wiki(tmp_path)
        store.save_source("c", "S", "u")
        
        config_dir = tmp_path / ".readpile"
        config_dir.mkdir(exist_ok=True)
        state_file = config_dir / "sync-state.json"
        
        from readpile.sync.state import SyncState
        state = SyncState(state_file)
        state.mark_pending("s1")
        state.mark_saved_url("https://example.com")
        state.commit()
        
        monkeypatch.setenv("READPILE_CONFIG", str(config_dir / "config.toml"))
        (config_dir / "config.toml").write_text(f'[sync]\nstate_file = "{state_file}"')
        
        result = runner.invoke(app, ["clean", "sources", "--wiki", str(wiki_path), "--force"])
        assert result.exit_code == 0
        
        state.load()
        assert len(state.get_pending()) == 0
        assert not state.is_saved_url("https://example.com")

    def test_clean_feeds_resets_state(self, tmp_path, monkeypatch):
        config_dir = tmp_path / ".readpile"
        config_dir.mkdir(exist_ok=True)
        feeds_toml = config_dir / "feeds.toml"
        feeds_toml.write_text("content")
        state_file = config_dir / "sync-state.json"
        
        from readpile.sync.state import SyncState
        state = SyncState(state_file)
        state.mark_url_seen("url", "feed")
        state.commit()
        
        monkeypatch.setenv("READPILE_CONFIG", str(config_dir / "config.toml"))
        (config_dir / "config.toml").write_text(f'[sync]\nstate_file = "{state_file}"')
        
        result = runner.invoke(app, ["clean", "feeds", "--force"])
        assert result.exit_code == 0
        
        state.load()
        assert "feed" not in state._data["feeds"]
