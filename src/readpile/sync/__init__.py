"""Sync pipeline — email, feeds, digest, synthesis CLI commands."""

from __future__ import annotations

from readpile.sync.state import SyncState
from readpile.sync.sources import SourceRegistry, Source
from readpile.sync.llm import generate
from readpile.sync.urls import normalize_url

__all__ = [
    "SyncState",
    "SourceRegistry",
    "Source",
    "generate",
    "normalize_url",
]
