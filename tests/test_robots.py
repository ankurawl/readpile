"""Tests for readpile.core.robots — robots.txt compliance checking."""

from unittest.mock import patch, MagicMock

import pytest

from readpile.core.robots import RobotsChecker


class TestRobotsChecker:
    def test_init_parses_robots_url(self):
        checker = RobotsChecker("https://example.com/some/page")
        assert checker.robots_url == "https://example.com/robots.txt"

    def test_allows_all_when_not_loaded(self):
        checker = RobotsChecker("https://example.com")
        assert checker.can_fetch("https://example.com/any/path") is True

    def test_crawl_delay_none_when_not_loaded(self):
        checker = RobotsChecker("https://example.com")
        assert checker.crawl_delay() is None

    def test_user_agent(self):
        assert RobotsChecker.USER_AGENT == "readpile/1.0"

    def test_load_handles_network_errors(self):
        checker = RobotsChecker("https://nonexistent.invalid/page")
        checker.load()
        assert checker._loaded is False
        assert checker.can_fetch("https://nonexistent.invalid/anything") is True
