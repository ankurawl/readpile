"""Tests for readpile.sync.synthesizer.Synthesizer."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def wiki_dir(tmp_path: Path) -> Path:
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / ".wiki.toml").write_text(
        'name = "test"\ncategories = ["concept", "summary", "entity"]\n'
    )
    (wiki / "pages").mkdir()
    (wiki / "sources").mkdir()
    (wiki / "index.md").write_text("# Index\n")
    (wiki / "log.md").write_text("# Log\n")
    return wiki


@pytest.fixture()
def state_dir(tmp_path: Path) -> Path:
    d = tmp_path / "state"
    d.mkdir()
    return d


@pytest.fixture()
def config(state_dir: Path, tmp_path: Path) -> dict:
    return {
        "sync": {
            "state_file": str(state_dir / "sync-state.json"),
            "log_file": str(tmp_path / "sync.log"),
            "synthesis_wait_days": 7,
            "synthesis_window_days": 90,
            "max_auto_synthesize_per_run": 20,
        },
        "llm": {
            "provider": "ollama",
            "model": "test-model",
        },
    }


def _write_state(state_dir: Path, pending: dict, skipped: dict | None = None) -> None:
    """Write a sync-state.json with the given pending items."""
    data = {
        "version": 1,
        "last_sync": None,
        "email": {"seen_ids": []},
        "feeds": {},
        "saved_urls": [],
        "synthesis": {
            "pending": pending,
            "synthesized": {},
            "skipped": skipped or {},
            "failed": {},
        },
        "digest": {"history": []},
    }
    (state_dir / "sync-state.json").write_text(json.dumps(data))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ---------------------------------------------------------------------------
# process_pending — 7-day wait logic
# ---------------------------------------------------------------------------


class TestProcessPending7DayWait:
    """Items younger than 7 days are skipped; older items auto-synthesized."""

    @pytest.mark.asyncio
    async def test_young_items_skipped(self, config, wiki_dir, state_dir):
        now = _now()
        # Item added 3 days ago — should be skipped
        _write_state(state_dir, {
            "sources/young.md": _iso(now - timedelta(days=3)),
        })
        # Write the source file so it can be found
        (wiki_dir / "sources" / "young.md").write_text(
            '---\ntitle: "Young"\n---\nContent'
        )

        from readpile.sync.synthesizer import Synthesizer

        synth = Synthesizer(config, wiki_dir)
        with (
            patch("readpile.sync.logging.setup_logging"),
            patch("readpile.sync.llm.generate") as mock_gen,
        ):
            await synth.process_pending()

        mock_gen.assert_not_called()

    @pytest.mark.asyncio
    async def test_old_items_synthesized(self, config, wiki_dir, state_dir):
        now = _now()
        # Item added 10 days ago — should be synthesized
        _write_state(state_dir, {
            "sources/old.md": _iso(now - timedelta(days=10)),
        })
        (wiki_dir / "sources" / "old.md").write_text(
            '---\ntitle: "Old Article"\n---\nSome interesting content here.'
        )

        from readpile.sync.synthesizer import Synthesizer

        page_content = (
            '---\ntitle: "Old Article Summary"\ncategory: concept\n'
            "tags: [test]\nsources: [sources/old.md]\nrelated: []\n"
            "source_date: 2025-01-01\ningested: 2025-05-01\nupdated: 2025-05-01\n"
            "---\nSynthesized content."
        )

        synth = Synthesizer(config, wiki_dir)
        with (
            patch("readpile.sync.logging.setup_logging"),
            patch("readpile.sync.llm.generate", return_value=page_content),
        ):
            await synth.process_pending()

        # A page should have been written
        pages = list((wiki_dir / "pages").glob("*.md"))
        assert len(pages) == 1


class TestProcessPending90DayCutoff:
    """Items older than 90 days are ignored."""

    @pytest.mark.asyncio
    async def test_ancient_items_ignored(self, config, wiki_dir, state_dir):
        now = _now()
        _write_state(state_dir, {
            "sources/ancient.md": _iso(now - timedelta(days=100)),
        })
        (wiki_dir / "sources" / "ancient.md").write_text(
            '---\ntitle: "Ancient"\n---\nContent'
        )

        from readpile.sync.synthesizer import Synthesizer

        synth = Synthesizer(config, wiki_dir)
        with (
            patch("readpile.sync.logging.setup_logging"),
            patch("readpile.sync.llm.generate") as mock_gen,
        ):
            await synth.process_pending()

        mock_gen.assert_not_called()


class TestMaxPerRunCap:
    """max_auto_synthesize_per_run caps processing, oldest first."""

    @pytest.mark.asyncio
    async def test_cap_at_20(self, config, wiki_dir, state_dir):
        now = _now()
        # Create 25 pending items, all older than 7 days
        pending = {}
        for i in range(25):
            path = f"sources/item-{i:03d}.md"
            pending[path] = _iso(now - timedelta(days=10 + i))
            (wiki_dir / "sources" / f"item-{i:03d}.md").write_text(
                f'---\ntitle: "Item {i}"\n---\nContent {i}'
            )

        _write_state(state_dir, pending)

        from readpile.sync.synthesizer import Synthesizer

        synth = Synthesizer(config, wiki_dir)
        call_count = 0

        def fake_generate(system, user, cfg):
            nonlocal call_count
            call_count += 1
            return "SKIP: redundant"

        with (
            patch("readpile.sync.logging.setup_logging"),
            patch("readpile.sync.llm.generate", side_effect=fake_generate),
        ):
            await synth.process_pending()

        assert call_count == 20


class TestProcessAll:
    """process_all ignores the 7-day wait."""

    @pytest.mark.asyncio
    async def test_process_all_ignores_wait(self, config, wiki_dir, state_dir):
        now = _now()
        _write_state(state_dir, {
            "sources/fresh.md": _iso(now - timedelta(days=1)),
        })
        (wiki_dir / "sources" / "fresh.md").write_text(
            '---\ntitle: "Fresh"\n---\nContent'
        )

        from readpile.sync.synthesizer import Synthesizer

        synth = Synthesizer(config, wiki_dir)
        with (
            patch("readpile.sync.logging.setup_logging"),
            patch(
                "readpile.sync.llm.generate",
                return_value="SKIP: redundant",
            ) as mock_gen,
        ):
            await synth.process_all()

        mock_gen.assert_called_once()


class TestProcessSource:
    """process_source synthesizes any source regardless of age."""

    @pytest.mark.asyncio
    async def test_process_source_any_age(self, config, wiki_dir, state_dir):
        (wiki_dir / "sources" / "specific.md").write_text(
            '---\ntitle: "Specific"\n---\nContent'
        )

        from readpile.sync.synthesizer import Synthesizer

        synth = Synthesizer(config, wiki_dir)
        with (
            patch("readpile.sync.logging.setup_logging"),
            patch(
                "readpile.sync.llm.generate",
                return_value="SKIP: no new info",
            ) as mock_gen,
        ):
            await synth.process_source("sources/specific.md")

        mock_gen.assert_called_once()


class TestLLMNewPage:
    """LLM creates a new page — verify write_page called."""

    @pytest.mark.asyncio
    async def test_llm_creates_page(self, config, wiki_dir, state_dir):
        now = _now()
        _write_state(state_dir, {
            "sources/article.md": _iso(now - timedelta(days=10)),
        })
        (wiki_dir / "sources" / "article.md").write_text(
            '---\ntitle: "Deep Learning Intro"\n---\nDeep learning content.'
        )

        page_content = (
            '---\ntitle: "Deep Learning Intro"\ncategory: concept\n'
            "tags: [ml, deep-learning]\nsources: [sources/article.md]\n"
            "related: []\nsource_date: 2025-01-01\n"
            "ingested: 2025-05-01\nupdated: 2025-05-01\n"
            "---\nDeep learning is a subset of machine learning."
        )

        from readpile.sync.synthesizer import Synthesizer

        synth = Synthesizer(config, wiki_dir)
        with (
            patch("readpile.sync.logging.setup_logging"),
            patch("readpile.sync.llm.generate", return_value=page_content),
        ):
            await synth.process_pending()

        pages = list((wiki_dir / "pages").glob("*.md"))
        assert len(pages) == 1
        assert "deep-learning" in pages[0].stem


class TestLLMSkipRedundant:
    """LLM SKIP response means no page is written."""

    @pytest.mark.asyncio
    async def test_skip_response_no_write(self, config, wiki_dir, state_dir):
        now = _now()
        _write_state(state_dir, {
            "sources/dup.md": _iso(now - timedelta(days=10)),
        })
        (wiki_dir / "sources" / "dup.md").write_text(
            '---\ntitle: "Duplicate"\n---\nSame content.'
        )

        from readpile.sync.synthesizer import Synthesizer

        synth = Synthesizer(config, wiki_dir)
        with (
            patch("readpile.sync.logging.setup_logging"),
            patch(
                "readpile.sync.llm.generate",
                return_value="SKIP: already covered by existing pages",
            ),
        ):
            await synth.process_pending()

        pages = list((wiki_dir / "pages").glob("*.md"))
        assert len(pages) == 0


class TestSlugCollision:
    """When a page with the same slug already exists, a disambiguator is appended."""

    @pytest.mark.asyncio
    async def test_slug_collision_appends_disambiguator(
        self, config, wiki_dir, state_dir,
    ):
        now = _now()
        # Pre-create a page with the slug "example-topic"
        (wiki_dir / "pages" / "example-topic.md").write_text(
            '---\ntitle: "Example Topic"\ncategory: concept\n'
            "tags: []\nsources: []\nrelated: []\n"
            "source_date: 2025-01-01\ningested: 2025-01-01\nupdated: 2025-01-01\n"
            "---\nExisting page."
        )

        _write_state(state_dir, {
            "sources/2025-03_new-article.md": _iso(now - timedelta(days=10)),
        })
        (wiki_dir / "sources" / "2025-03_new-article.md").write_text(
            '---\ntitle: "Example Topic"\n---\nNew content about example topic.'
        )

        page_content = (
            '---\ntitle: "Example Topic"\ncategory: concept\n'
            "tags: [test]\nsources: [sources/2025-03_new-article.md]\nrelated: []\n"
            "source_date: 2025-03-01\ningested: 2025-05-01\nupdated: 2025-05-01\n"
            "---\nNew perspective on example topic."
        )

        from readpile.sync.synthesizer import Synthesizer

        synth = Synthesizer(config, wiki_dir)
        with (
            patch("readpile.sync.logging.setup_logging"),
            patch("readpile.sync.llm.generate", return_value=page_content),
            patch("readpile.wiki.store.WikiStore.search", return_value=[]),
        ):
            await synth.process_pending()

        pages = list((wiki_dir / "pages").glob("*.md"))
        assert len(pages) == 2
        stems = {p.stem for p in pages}
        assert "example-topic" in stems
        disambiguated = stems - {"example-topic"}
        assert len(disambiguated) == 1
        assert disambiguated.pop().startswith("example-topic-")


class TestNonASCIITitle:
    """Non-ASCII title produces a hash-based filename."""

    def test_make_slug_non_ascii(self):
        from readpile.sync.synthesizer import Synthesizer

        synth = Synthesizer.__new__(Synthesizer)
        slug = synth._make_slug("深层学习入门")  # Chinese characters
        # All non-ASCII chars are stripped, leaving empty -> hash-based fallback
        assert slug.startswith("page-")
        assert len(slug) > 5


class TestYAMLValidationRepair:
    """YAML validation failure triggers repair; unfixable -> synthesis_failed."""

    @pytest.mark.asyncio
    async def test_yaml_repair_attempted(self, config, wiki_dir, state_dir):
        now = _now()
        _write_state(state_dir, {
            "sources/bad-yaml.md": _iso(now - timedelta(days=10)),
        })
        (wiki_dir / "sources" / "bad-yaml.md").write_text(
            '---\ntitle: "Bad YAML"\n---\nContent.'
        )

        # Content with unquoted title containing colons — will fail validation
        bad_content = (
            "---\ntitle: Bad: Title: Here\ncategory: concept\n"
            "tags: [test]\nsources: []\nrelated: []\n"
            "source_date: 2025-01-01\ningested: 2025-05-01\nupdated: 2025-05-01\n"
            "---\nBody content."
        )

        from readpile.sync.synthesizer import Synthesizer

        synth = Synthesizer(config, wiki_dir)
        # Make write_page always fail with ValueError to simulate YAML issues
        with (
            patch("readpile.sync.logging.setup_logging"),
            patch("readpile.sync.llm.generate", return_value=bad_content),
            patch("readpile.wiki.store.WikiStore.search", return_value=[]),
            patch(
                "readpile.wiki.store.WikiStore.write_page",
                side_effect=ValueError("invalid YAML frontmatter"),
            ),
        ):
            await synth.process_pending()

        # Verify state was updated — either synthesized (repair succeeded) or failed
        state_data = json.loads(
            (state_dir / "sync-state.json").read_text()
        )
        synth_data = state_data["synthesis"]
        path_key = "sources/bad-yaml.md"
        assert (
            path_key in synth_data["failed"]
            or path_key in synth_data["synthesized"]
        )


class TestDryRunMode:
    """dry_run mode does not write any pages."""

    @pytest.mark.asyncio
    async def test_dry_run_no_writes(self, config, wiki_dir, state_dir):
        now = _now()
        _write_state(state_dir, {
            "sources/test.md": _iso(now - timedelta(days=10)),
        })
        (wiki_dir / "sources" / "test.md").write_text(
            '---\ntitle: "Test"\n---\nContent.'
        )

        from readpile.sync.synthesizer import Synthesizer

        synth = Synthesizer(config, wiki_dir, dry_run=True)
        with (
            patch("readpile.sync.logging.setup_logging"),
            patch("readpile.sync.llm.generate") as mock_gen,
        ):
            await synth.process_pending()

        mock_gen.assert_not_called()
        pages = list((wiki_dir / "pages").glob("*.md"))
        assert len(pages) == 0
