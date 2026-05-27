"""Configuration — load and validate readpile settings."""

from __future__ import annotations

import copy
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULTS: dict = {
    "general": {
        "date_format": "YYYY-MM-DD",
        "filename_max_length": 80,
    },
    "transcribe": {
        "engine": "auto",
        "whisper_model": "base",
        "diarize": False,
    },
    "scrape": {
        "headless": True,
        "respect_robots": True,
        "rate_limit": 1.0,
    },
    "crawl": {
        "max_depth": 10,
        "max_pages": 100,
    },
    "wiki": {
        "default_dir": "~/my-wiki",
    },
    "llm": {
        "base_url": "anthropic",
        "model": "claude-sonnet-4-6",
    },
    "sync": {
        "state_file": "~/.readpile/sync-state.json",
        "log_file": "~/.readpile/sync.log",
        "synthesis_wait_days": 7,
        "synthesis_window_days": 90,
        "max_auto_synthesize_per_run": 20,
        "max_initial_entries": 20,
        "max_consecutive_failures": 7,
        "max_email_size_bytes": 5242880,
        "email": {
            "enabled": False,
            "provider": "gmail",
            "account": "",
            "credentials_file": "~/.readpile/email-credentials.json",
            "labels": ["INBOX"],
            "max_age_days": 7,
            "trusted_senders": [],
        },
        "digest": {
            "enabled": False,
            "to": "",
            "from": "",
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "max_topic_files": 5,
            "max_pending_digests": 7,
            "wiki_health_day": "saturday",
        },
    },
}

# ---------------------------------------------------------------------------
# Environment variable -> config path mapping
# ---------------------------------------------------------------------------

ENV_MAP: dict[str, tuple[str, ...]] = {}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base* (override wins).

    Returns the mutated *base* dict for convenience.
    """
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _load_toml(path: Path) -> dict:
    """Load a TOML file and return its contents as a dict.

    Uses ``tomllib`` (Python 3.11+) with a ``tomli`` fallback for 3.10.
    """
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

    with open(path, "rb") as fh:
        return tomllib.load(fh)


def _apply_env_overlay(config: dict) -> None:
    """Write environment variable values into *config* at the paths defined
    in :data:`ENV_MAP`.  Only variables that are actually set in
    ``os.environ`` are applied.
    """
    for env_var, path in ENV_MAP.items():
        value = os.environ.get(env_var)
        if value is None:
            continue
        # Walk to the parent dict, creating intermediate dicts as needed.
        node = config
        for part in path[:-1]:
            node = node.setdefault(part, {})
        node[path[-1]] = value


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_config_path() -> Path:
    """Return the path to the readpile config file.

    Respects the ``READPILE_CONFIG`` environment variable; falls back to
    ``~/.readpile/config.toml``.
    """
    env = os.environ.get("READPILE_CONFIG")
    if env:
        return Path(env).expanduser()
    return Path("~/.readpile/config.toml").expanduser()


def load_config(cli_overrides: dict | None = None) -> dict:
    """Load the merged configuration with the following precedence
    (highest wins first):

    1. *cli_overrides* dict
    2. Environment variables (see :data:`ENV_MAP`)
    3. TOML config file (see :func:`get_config_path`)
    4. Built-in :data:`DEFAULTS`
    """
    config = copy.deepcopy(DEFAULTS)

    # Layer: config file
    config_path = get_config_path()
    if config_path.exists():
        file_config = _load_toml(config_path)
        _deep_merge(config, file_config)

    # Layer: environment variables
    _apply_env_overlay(config)

    # Layer: CLI overrides
    if cli_overrides:
        _deep_merge(config, cli_overrides)

    return config
