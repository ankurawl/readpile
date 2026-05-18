"""Tests for readpile.wiki.models — WikiConfig and WikiPage."""

from datetime import date

import pytest

from readpile.wiki.models import WikiConfig, WikiPage


# --- WikiConfig ---


class TestWikiConfig:
    def test_from_toml(self):
        toml_text = '''
[wiki]
name = "AI Research"
description = "Personal ML knowledge base"

[conventions]
categories = ["concept", "entity", "summary"]
link_style = "[[page-name]]"
'''
        config = WikiConfig.from_toml(toml_text)
        assert config.name == "AI Research"
        assert config.description == "Personal ML knowledge base"
        assert config.categories == ["concept", "entity", "summary"]

    def test_from_toml_defaults(self):
        toml_text = '''
[wiki]
name = "Minimal"
'''
        config = WikiConfig.from_toml(toml_text)
        assert config.name == "Minimal"
        assert config.description == ""
        assert "concept" in config.categories
        assert "exploration" in config.categories

    def test_to_toml_roundtrip(self):
        config = WikiConfig(name="Test", description="Desc", categories=["concept", "entity"])
        toml_str = config.to_toml()
        restored = WikiConfig.from_toml(toml_str)
        assert restored.name == config.name
        assert restored.description == config.description
        assert restored.categories == config.categories

    def test_to_toml_format(self):
        config = WikiConfig(name="Wiki", description="My wiki")
        text = config.to_toml()
        assert '[wiki]' in text
        assert 'name = "Wiki"' in text
        assert '[conventions]' in text


# --- WikiPage ---


class TestWikiPage:
    def test_from_markdown_complete(self):
        md = '''---
title: "Attention Mechanism"
category: concept
tags: [transformers, deep-learning]
sources: [sources/2026-05-10_article.md]
related: [transformers, andrej-karpathy]
source_date: 2026-05-08
ingested: 2026-05-10
updated: 2026-05-17
---

The attention mechanism allows neural networks to focus.

## See Also

- [[transformers]]
'''
        page = WikiPage.from_markdown(md)
        assert page.title == "Attention Mechanism"
        assert page.category == "concept"
        assert page.tags == ["transformers", "deep-learning"]
        assert page.sources == ["sources/2026-05-10_article.md"]
        assert page.related == ["transformers", "andrej-karpathy"]
        assert page.source_date == date(2026, 5, 8)
        assert page.ingested == date(2026, 5, 10)
        assert page.updated == date(2026, 5, 17)
        assert "[[transformers]]" in page.body

    def test_from_markdown_minimal(self):
        md = '''---
title: Minimal Page
category: entity
ingested: 2026-05-17
updated: 2026-05-17
---

Just the basics.
'''
        page = WikiPage.from_markdown(md)
        assert page.title == "Minimal Page"
        assert page.category == "entity"
        assert page.tags == []
        assert page.sources == []
        assert page.related == []
        assert page.source_date is None

    def test_from_markdown_missing_required(self):
        md = '''---
title: No Category
ingested: 2026-05-17
updated: 2026-05-17
---

Missing category.
'''
        with pytest.raises(ValueError, match="category"):
            WikiPage.from_markdown(md)

    def test_from_markdown_missing_title(self):
        md = '''---
category: concept
ingested: 2026-05-17
updated: 2026-05-17
---

Missing title.
'''
        with pytest.raises(ValueError, match="title"):
            WikiPage.from_markdown(md)

    def test_from_markdown_missing_ingested(self):
        md = '''---
title: Test
category: concept
updated: 2026-05-17
---

Body.
'''
        with pytest.raises(ValueError, match="ingested"):
            WikiPage.from_markdown(md)

    def test_from_markdown_no_frontmatter(self):
        with pytest.raises(ValueError, match="---"):
            WikiPage.from_markdown("Just plain text")

    def test_source_date_optional(self):
        md = '''---
title: No Source Date
category: summary
ingested: 2026-05-17
updated: 2026-05-17
---

No source date.
'''
        page = WikiPage.from_markdown(md)
        assert page.source_date is None

    def test_to_markdown_roundtrip(self):
        original = WikiPage(
            title="Roundtrip Test",
            category="concept",
            tags=["a", "b"],
            sources=["sources/test.md"],
            related=["other-page"],
            source_date=date(2026, 1, 15),
            ingested=date(2026, 5, 10),
            updated=date(2026, 5, 17),
            body="Content body here.",
        )
        md = original.to_markdown()
        restored = WikiPage.from_markdown(md)
        assert restored.title == original.title
        assert restored.category == original.category
        assert restored.tags == original.tags
        assert restored.sources == original.sources
        assert restored.related == original.related
        assert restored.source_date == original.source_date
        assert restored.ingested == original.ingested
        assert restored.updated == original.updated
        assert "Content body here." in restored.body

    def test_to_markdown_three_timestamps(self):
        page = WikiPage(
            title="Timestamp Test",
            category="entity",
            source_date=date(2025, 3, 1),
            ingested=date(2026, 5, 10),
            updated=date(2026, 5, 17),
            body="Body.",
        )
        md = page.to_markdown()
        assert "source_date: '2025-03-01'" in md or "source_date: 2025-03-01" in md
        assert "ingested: '2026-05-10'" in md or "ingested: 2026-05-10" in md
        assert "updated: '2026-05-17'" in md or "updated: 2026-05-17" in md

    def test_wikilinks_in_body(self):
        md = '''---
title: Links Test
category: concept
ingested: 2026-05-17
updated: 2026-05-17
---

See [[transformers]] and [[attention-mechanism]].
'''
        page = WikiPage.from_markdown(md)
        assert "[[transformers]]" in page.body
        assert "[[attention-mechanism]]" in page.body
