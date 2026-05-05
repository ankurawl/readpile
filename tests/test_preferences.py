"""Tests for readpile.bot.preferences — per-user configuration storage."""

import json
import os

import pytest

from readpile.bot.preferences import (
    DEFAULT_PREFERENCES,
    VALID_PREF_KEYS,
    VALID_STYLES,
    add_to_history,
    get_history,
    get_preferences,
    set_preference,
)


@pytest.fixture
def data_dir(tmp_path):
    """Provide a temporary data directory."""
    return str(tmp_path)


class TestGetPreferences:
    def test_returns_defaults_for_unknown_user(self, data_dir):
        prefs = get_preferences(12345, data_dir)
        assert prefs["language"] == "en"
        assert prefs["style"] == "detailed"

    def test_returns_saved_preferences(self, data_dir):
        set_preference(12345, "language", "es", data_dir)
        prefs = get_preferences(12345, data_dir)
        assert prefs["language"] == "es"
        # style should still be the default
        assert prefs["style"] == "detailed"

    def test_returns_copy_not_reference(self, data_dir):
        prefs1 = get_preferences(12345, data_dir)
        prefs2 = get_preferences(12345, data_dir)
        prefs1["language"] = "fr"
        assert prefs2["language"] == "en"


class TestSetPreference:
    def test_set_language(self, data_dir):
        set_preference(42, "language", "hi", data_dir)
        prefs = get_preferences(42, data_dir)
        assert prefs["language"] == "hi"

    def test_set_style_brief(self, data_dir):
        set_preference(42, "style", "brief", data_dir)
        prefs = get_preferences(42, data_dir)
        assert prefs["style"] == "brief"

    def test_set_style_detailed(self, data_dir):
        set_preference(42, "style", "detailed", data_dir)
        prefs = get_preferences(42, data_dir)
        assert prefs["style"] == "detailed"

    def test_rejects_invalid_key(self, data_dir):
        with pytest.raises(ValueError, match="Invalid preference key"):
            set_preference(42, "invalid_key", "value", data_dir)

    def test_rejects_invalid_style(self, data_dir):
        with pytest.raises(ValueError, match="Invalid style"):
            set_preference(42, "style", "super_detailed", data_dir)

    def test_persists_to_disk(self, data_dir):
        set_preference(42, "language", "de", data_dir)
        path = os.path.join(data_dir, "preferences.json")
        assert os.path.exists(path)

        with open(path) as f:
            data = json.load(f)
        assert data["42"]["language"] == "de"

    def test_multiple_users_independent(self, data_dir):
        set_preference(1, "language", "fr", data_dir)
        set_preference(2, "language", "ja", data_dir)

        assert get_preferences(1, data_dir)["language"] == "fr"
        assert get_preferences(2, data_dir)["language"] == "ja"


class TestHistory:
    def test_add_to_history(self, data_dir):
        add_to_history(42, {"title": "Test Video", "url": "https://example.com"}, data_dir)
        history = get_history(42, data_dir)
        assert len(history) == 1
        assert history[0]["title"] == "Test Video"
        assert "processed_at" in history[0]

    def test_history_limit_20(self, data_dir):
        for i in range(25):
            add_to_history(42, {"title": f"Video {i}"}, data_dir)

        history = get_history(42, data_dir)
        assert len(history) == 20
        # Should keep the last 20 (index 5-24)
        assert history[0]["title"] == "Video 5"
        assert history[-1]["title"] == "Video 24"

    def test_empty_history_for_new_user(self, data_dir):
        history = get_history(99, data_dir)
        assert history == []

    def test_history_per_user(self, data_dir):
        add_to_history(1, {"title": "User 1 Video"}, data_dir)
        add_to_history(2, {"title": "User 2 Video"}, data_dir)

        h1 = get_history(1, data_dir)
        h2 = get_history(2, data_dir)

        assert len(h1) == 1
        assert len(h2) == 1
        assert h1[0]["title"] == "User 1 Video"
        assert h2[0]["title"] == "User 2 Video"
