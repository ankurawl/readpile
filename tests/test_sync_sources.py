"""Tests for readpile.sync.sources — SourceRegistry with tomlkit round-trip."""

from __future__ import annotations

from pathlib import Path

import pytest
import tomlkit

from readpile.sync.sources import SourceRegistry, Source


# --- Helpers ---


def _write_sources_toml(path: Path, sources: list[dict]) -> None:
    """Write a sources.toml file using tomlkit."""
    doc = tomlkit.document()
    aot = tomlkit.aot()
    for s in sources:
        table = tomlkit.table()
        for k, v in s.items():
            table.add(k, v)
        aot.append(table)
    doc.add("sources", aot)
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")


# --- Load from sources.toml ---


class TestLoad:
    def test_load_multiple_sources(self, tmp_path):
        sources_file = tmp_path / "sources.toml"
        _write_sources_toml(sources_file, [
            {"name": "blog-a", "url": "https://a.com/feed.xml", "kind": "rss"},
            {"name": "yt-channel", "url": "https://youtube.com/@chan", "kind": "youtube"},
            {"name": "pod-show", "url": "https://pod.com/rss", "kind": "podcast"},
        ])

        registry = SourceRegistry(sources_file)
        sources = registry.load()
        assert len(sources) == 3
        assert sources[0].name == "blog-a"
        assert sources[0].url == "https://a.com/feed.xml"
        assert sources[0].kind == "rss"
        assert sources[1].kind == "youtube"
        assert sources[2].kind == "podcast"

    def test_load_defaults_synthesize_true_disabled_false(self, tmp_path):
        sources_file = tmp_path / "sources.toml"
        _write_sources_toml(sources_file, [
            {"name": "basic", "url": "https://x.com/feed", "kind": "rss"},
        ])

        registry = SourceRegistry(sources_file)
        sources = registry.load()
        assert sources[0].synthesize is True
        assert sources[0].disabled is False

    def test_load_respects_synthesize_false(self, tmp_path):
        sources_file = tmp_path / "sources.toml"
        _write_sources_toml(sources_file, [
            {"name": "nosyn", "url": "https://x.com/feed", "kind": "rss", "synthesize": False},
        ])

        registry = SourceRegistry(sources_file)
        sources = registry.load()
        assert sources[0].synthesize is False

    def test_load_respects_disabled_true(self, tmp_path):
        sources_file = tmp_path / "sources.toml"
        _write_sources_toml(sources_file, [
            {"name": "off", "url": "https://x.com/feed", "kind": "rss", "disabled": True},
        ])

        registry = SourceRegistry(sources_file)
        sources = registry.load()
        assert sources[0].disabled is True


# --- Add source round-trip ---


class TestAdd:
    def test_add_creates_entry(self, tmp_path):
        sources_file = tmp_path / "sources.toml"
        _write_sources_toml(sources_file, [
            {"name": "existing", "url": "https://a.com/feed", "kind": "rss"},
        ])

        registry = SourceRegistry(sources_file)
        registry.load()
        registry.add(Source(name="new-blog", url="https://b.com/feed", kind="rss"))

        # Reload and verify
        registry2 = SourceRegistry(sources_file)
        sources = registry2.load()
        assert len(sources) == 2
        assert sources[1].name == "new-blog"

    def test_add_preserves_comments(self, tmp_path):
        sources_file = tmp_path / "sources.toml"
        # Write TOML with a comment
        content = '# My feed sources\n\n[[sources]]\nname = "blog-a"\nurl = "https://a.com/feed"\nkind = "rss"\n'
        sources_file.write_text(content, encoding="utf-8")

        registry = SourceRegistry(sources_file)
        registry.load()
        registry.add(Source(name="blog-b", url="https://b.com/feed", kind="rss"))

        text = sources_file.read_text(encoding="utf-8")
        assert "# My feed sources" in text
        assert "blog-b" in text

    def test_add_writes_synthesize_false_when_set(self, tmp_path):
        sources_file = tmp_path / "sources.toml"

        registry = SourceRegistry(sources_file)
        registry.add(Source(name="raw-only", url="https://x.com/feed", kind="rss", synthesize=False))

        text = sources_file.read_text(encoding="utf-8")
        assert "synthesize = false" in text

    def test_add_writes_disabled_true_when_set(self, tmp_path):
        sources_file = tmp_path / "sources.toml"

        registry = SourceRegistry(sources_file)
        registry.add(Source(name="paused", url="https://x.com/feed", kind="rss", disabled=True))

        text = sources_file.read_text(encoding="utf-8")
        assert "disabled = true" in text

    def test_add_omits_synthesize_when_default_true(self, tmp_path):
        sources_file = tmp_path / "sources.toml"

        registry = SourceRegistry(sources_file)
        registry.add(Source(name="normal", url="https://x.com/feed", kind="rss"))

        text = sources_file.read_text(encoding="utf-8")
        assert "synthesize" not in text

    def test_missing_file_creates_new_on_add(self, tmp_path):
        sources_file = tmp_path / "new_dir" / "sources.toml"
        assert not sources_file.exists()

        registry = SourceRegistry(sources_file)
        registry.add(Source(name="first", url="https://a.com/feed", kind="rss"))

        assert sources_file.exists()
        registry2 = SourceRegistry(sources_file)
        sources = registry2.load()
        assert len(sources) == 1
        assert sources[0].name == "first"


# --- Remove source ---


class TestRemove:
    def test_remove_by_name(self, tmp_path):
        sources_file = tmp_path / "sources.toml"
        _write_sources_toml(sources_file, [
            {"name": "keep-me", "url": "https://a.com/feed", "kind": "rss"},
            {"name": "remove-me", "url": "https://b.com/feed", "kind": "rss"},
        ])

        registry = SourceRegistry(sources_file)
        registry.load()
        registry.remove("remove-me")

        registry2 = SourceRegistry(sources_file)
        sources = registry2.load()
        assert len(sources) == 1
        assert sources[0].name == "keep-me"

    def test_remove_missing_raises_keyerror(self, tmp_path):
        sources_file = tmp_path / "sources.toml"
        _write_sources_toml(sources_file, [
            {"name": "only-one", "url": "https://a.com/feed", "kind": "rss"},
        ])

        registry = SourceRegistry(sources_file)
        registry.load()
        with pytest.raises(KeyError, match="nonexistent"):
            registry.remove("nonexistent")


# --- Enable / Disable ---


class TestEnableDisable:
    def test_disable_source(self, tmp_path):
        sources_file = tmp_path / "sources.toml"
        _write_sources_toml(sources_file, [
            {"name": "toggle-me", "url": "https://a.com/feed", "kind": "rss"},
        ])

        registry = SourceRegistry(sources_file)
        registry.load()
        registry.disable("toggle-me")

        registry2 = SourceRegistry(sources_file)
        sources = registry2.load()
        assert sources[0].disabled is True

    def test_enable_source(self, tmp_path):
        sources_file = tmp_path / "sources.toml"
        _write_sources_toml(sources_file, [
            {"name": "toggle-me", "url": "https://a.com/feed", "kind": "rss", "disabled": True},
        ])

        registry = SourceRegistry(sources_file)
        registry.load()
        registry.enable("toggle-me")

        registry2 = SourceRegistry(sources_file)
        sources = registry2.load()
        assert sources[0].disabled is False

    def test_enable_missing_raises_keyerror(self, tmp_path):
        sources_file = tmp_path / "sources.toml"
        _write_sources_toml(sources_file, [])

        registry = SourceRegistry(sources_file)
        registry.load()
        with pytest.raises(KeyError, match="ghost"):
            registry.enable("ghost")

    def test_disable_missing_raises_keyerror(self, tmp_path):
        sources_file = tmp_path / "sources.toml"
        _write_sources_toml(sources_file, [])

        registry = SourceRegistry(sources_file)
        registry.load()
        with pytest.raises(KeyError, match="ghost"):
            registry.disable("ghost")


# --- update_url ---


class TestUpdateUrl:
    def test_update_url_for_redirect(self, tmp_path):
        sources_file = tmp_path / "sources.toml"
        _write_sources_toml(sources_file, [
            {"name": "moved", "url": "https://old.com/feed", "kind": "rss"},
        ])

        registry = SourceRegistry(sources_file)
        registry.load()
        registry.update_url("moved", "https://new.com/feed")

        registry2 = SourceRegistry(sources_file)
        sources = registry2.load()
        assert sources[0].url == "https://new.com/feed"

    def test_update_url_missing_raises_keyerror(self, tmp_path):
        sources_file = tmp_path / "sources.toml"
        _write_sources_toml(sources_file, [
            {"name": "existing", "url": "https://a.com/feed", "kind": "rss"},
        ])

        registry = SourceRegistry(sources_file)
        registry.load()
        with pytest.raises(KeyError, match="no-such"):
            registry.update_url("no-such", "https://x.com/feed")


# --- Empty file handling ---


class TestEmptyFile:
    def test_empty_file_returns_no_sources(self, tmp_path):
        sources_file = tmp_path / "sources.toml"
        sources_file.write_text("", encoding="utf-8")

        registry = SourceRegistry(sources_file)
        sources = registry.load()
        assert sources == []

    def test_missing_file_returns_no_sources(self, tmp_path):
        sources_file = tmp_path / "sources.toml"
        assert not sources_file.exists()

        registry = SourceRegistry(sources_file)
        sources = registry.load()
        assert sources == []


# --- Field preservation in TOML ---


class TestFieldPreservation:
    def test_synthesize_false_preserved_across_operations(self, tmp_path):
        sources_file = tmp_path / "sources.toml"
        _write_sources_toml(sources_file, [
            {"name": "no-synth", "url": "https://x.com/feed", "kind": "rss", "synthesize": False},
            {"name": "normal", "url": "https://y.com/feed", "kind": "rss"},
        ])

        # Disable the second source — should not affect first
        registry = SourceRegistry(sources_file)
        registry.load()
        registry.disable("normal")

        registry2 = SourceRegistry(sources_file)
        sources = registry2.load()
        assert sources[0].synthesize is False
        assert sources[1].disabled is True

    def test_disabled_true_preserved_across_add(self, tmp_path):
        sources_file = tmp_path / "sources.toml"
        _write_sources_toml(sources_file, [
            {"name": "off", "url": "https://x.com/feed", "kind": "rss", "disabled": True},
        ])

        registry = SourceRegistry(sources_file)
        registry.load()
        registry.add(Source(name="new", url="https://z.com/feed", kind="youtube"))

        registry2 = SourceRegistry(sources_file)
        sources = registry2.load()
        assert sources[0].disabled is True
        assert len(sources) == 2
