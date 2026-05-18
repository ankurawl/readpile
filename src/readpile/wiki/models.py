"""Wiki data models — WikiConfig and WikiPage dataclasses."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

import yaml


@dataclass
class WikiConfig:
    """Parsed .wiki.toml configuration."""

    name: str
    description: str = ""
    categories: list[str] = field(default_factory=lambda: [
        "concept", "entity", "summary", "comparison", "exploration", "reference",
    ])

    @classmethod
    def from_toml(cls, text: str) -> WikiConfig:
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib  # type: ignore[no-redef]

        data = tomllib.loads(text)
        wiki = data.get("wiki", {})
        conventions = data.get("conventions", {})
        return cls(
            name=wiki.get("name", ""),
            description=wiki.get("description", ""),
            categories=conventions.get("categories", cls.__dataclass_fields__["categories"].default_factory()),
        )

    def to_toml(self) -> str:
        cats = ", ".join(f'"{c}"' for c in self.categories)
        return (
            f'[wiki]\nname = "{self.name}"\n'
            f'description = "{self.description}"\n\n'
            f'[conventions]\ncategories = [{cats}]\n'
            f'link_style = "[[page-name]]"\n'
        )


@dataclass
class WikiPage:
    """A wiki page with parsed frontmatter and body."""

    title: str
    category: str
    ingested: date
    updated: date
    tags: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    source_date: date | None = None
    body: str = ""

    @classmethod
    def from_markdown(cls, text: str) -> WikiPage:
        text = text.strip()
        if not text.startswith("---"):
            raise ValueError("Wiki page must start with '---' YAML front matter delimiter")

        second_delim = text.index("---", 3)
        yaml_block = text[3:second_delim].strip()
        body = text[second_delim + 3:].strip()

        meta = yaml.safe_load(yaml_block)
        if not isinstance(meta, dict):
            raise ValueError("Invalid YAML frontmatter")

        for required in ("title", "category", "ingested", "updated"):
            if required not in meta:
                raise ValueError(f"Missing required frontmatter field: {required}")

        def _parse_date(val: str | date | None) -> date | None:
            if val is None:
                return None
            if isinstance(val, date):
                return val
            return date.fromisoformat(str(val))

        def _ensure_list(val) -> list[str]:
            if val is None:
                return []
            if isinstance(val, list):
                return [str(v) for v in val]
            return [str(val)]

        return cls(
            title=str(meta["title"]),
            category=str(meta["category"]),
            ingested=_parse_date(meta["ingested"]),
            updated=_parse_date(meta["updated"]),
            tags=_ensure_list(meta.get("tags")),
            sources=_ensure_list(meta.get("sources")),
            related=_ensure_list(meta.get("related")),
            source_date=_parse_date(meta.get("source_date")),
            body=body,
        )

    def to_markdown(self) -> str:
        meta: dict = {
            "title": self.title,
            "category": self.category,
        }
        if self.tags:
            meta["tags"] = self.tags
        if self.sources:
            meta["sources"] = self.sources
        if self.related:
            meta["related"] = self.related
        if self.source_date is not None:
            meta["source_date"] = self.source_date.isoformat()
        meta["ingested"] = self.ingested.isoformat()
        meta["updated"] = self.updated.isoformat()

        front = yaml.dump(meta, default_flow_style=False, sort_keys=False).strip()
        return f"---\n{front}\n---\n\n{self.body}\n"
