"""Tests for readpile.bot.whitelist — authorized user/chat management."""

import json
import os
import tempfile

import pytest

from readpile.bot.whitelist import (
    add_to_whitelist,
    is_whitelisted,
    load_whitelist,
    remove_from_whitelist,
    save_whitelist,
)


@pytest.fixture
def data_dir(tmp_path):
    """Provide a temporary data directory."""
    return str(tmp_path)


class TestLoadWhitelist:
    def test_creates_file_if_missing(self, data_dir):
        wl = load_whitelist(data_dir)
        assert wl == set()
        assert os.path.exists(os.path.join(data_dir, "whitelist.json"))

    def test_reads_existing_file(self, data_dir):
        path = os.path.join(data_dir, "whitelist.json")
        os.makedirs(data_dir, exist_ok=True)
        with open(path, "w") as f:
            json.dump([111, 222, 333], f)

        wl = load_whitelist(data_dir)
        assert wl == {111, 222, 333}

    def test_handles_corrupt_json(self, data_dir):
        path = os.path.join(data_dir, "whitelist.json")
        os.makedirs(data_dir, exist_ok=True)
        with open(path, "w") as f:
            f.write("not valid json!!!")

        wl = load_whitelist(data_dir)
        assert wl == set()

    def test_returns_set_of_ints(self, data_dir):
        path = os.path.join(data_dir, "whitelist.json")
        os.makedirs(data_dir, exist_ok=True)
        with open(path, "w") as f:
            json.dump([100, 200], f)

        wl = load_whitelist(data_dir)
        assert isinstance(wl, set)
        for item in wl:
            assert isinstance(item, int)


class TestSaveWhitelist:
    def test_saves_sorted_list(self, data_dir):
        save_whitelist({300, 100, 200}, data_dir)

        path = os.path.join(data_dir, "whitelist.json")
        with open(path) as f:
            data = json.load(f)

        assert data == [100, 200, 300]

    def test_creates_data_dir_if_missing(self, tmp_path):
        nested = str(tmp_path / "sub" / "dir")
        save_whitelist({42}, nested)

        path = os.path.join(nested, "whitelist.json")
        assert os.path.exists(path)


class TestIsWhitelisted:
    def test_admin_always_allowed(self, data_dir):
        assert is_whitelisted(12345, 12345, data_dir) is True

    def test_whitelisted_user_allowed(self, data_dir):
        save_whitelist({99}, data_dir)
        assert is_whitelisted(99, 12345, data_dir) is True

    def test_non_whitelisted_user_denied(self, data_dir):
        save_whitelist({99}, data_dir)
        assert is_whitelisted(88, 12345, data_dir) is False


class TestAddToWhitelist:
    def test_adds_new_user(self, data_dir):
        result = add_to_whitelist(42, data_dir)
        assert result is True
        assert 42 in load_whitelist(data_dir)

    def test_returns_false_if_already_present(self, data_dir):
        add_to_whitelist(42, data_dir)
        result = add_to_whitelist(42, data_dir)
        assert result is False


class TestRemoveFromWhitelist:
    def test_removes_existing_user(self, data_dir):
        add_to_whitelist(42, data_dir)
        result = remove_from_whitelist(42, data_dir)
        assert result is True
        assert 42 not in load_whitelist(data_dir)

    def test_returns_false_if_not_present(self, data_dir):
        result = remove_from_whitelist(999, data_dir)
        assert result is False
