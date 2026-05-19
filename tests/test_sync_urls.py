"""Tests for readpile.sync.urls — URL normalization for dedup."""

from __future__ import annotations

import pytest

from readpile.sync.urls import normalize_url


# --- Tracking param stripping ---


class TestTrackingParamStripping:
    def test_strips_utm_source(self):
        url = "https://example.com/post?utm_source=twitter"
        assert normalize_url(url) == "https://example.com/post"

    def test_strips_utm_medium(self):
        url = "https://example.com/post?utm_medium=social"
        assert normalize_url(url) == "https://example.com/post"

    def test_strips_utm_campaign(self):
        url = "https://example.com/post?utm_campaign=launch"
        assert normalize_url(url) == "https://example.com/post"

    def test_strips_ref(self):
        url = "https://example.com/post?ref=homepage"
        assert normalize_url(url) == "https://example.com/post"

    def test_strips_fbclid(self):
        url = "https://example.com/post?fbclid=abc123def456"
        assert normalize_url(url) == "https://example.com/post"

    def test_strips_gclid(self):
        url = "https://example.com/post?gclid=Cj0KCQjw"
        assert normalize_url(url) == "https://example.com/post"

    def test_strips_multiple_tracking_params(self):
        url = "https://example.com/post?utm_source=tw&utm_medium=social&utm_campaign=q1&ref=nav"
        assert normalize_url(url) == "https://example.com/post"


# --- Trailing slash ---


class TestTrailingSlash:
    def test_removes_trailing_slash(self):
        assert normalize_url("https://example.com/blog/") == "https://example.com/blog"

    def test_no_trailing_slash_unchanged(self):
        assert normalize_url("https://example.com/blog") == "https://example.com/blog"

    def test_root_path_trailing_slash_removed(self):
        result = normalize_url("https://example.com/")
        assert result == "https://example.com"


# --- www prefix ---


class TestWwwPrefix:
    def test_strips_www(self):
        assert normalize_url("https://www.example.com/post") == "https://example.com/post"

    def test_no_www_unchanged(self):
        assert normalize_url("https://example.com/post") == "https://example.com/post"


# --- Hostname lowercasing ---


class TestHostnameLowercase:
    def test_lowercases_hostname(self):
        assert normalize_url("https://EXAMPLE.COM/post") == "https://example.com/post"

    def test_mixed_case_hostname(self):
        assert normalize_url("https://Blog.Example.Com/post") == "https://blog.example.com/post"


# --- Path and fragment preservation ---


class TestPreservation:
    def test_preserves_path(self):
        result = normalize_url("https://example.com/blog/2024/my-post")
        assert result == "https://example.com/blog/2024/my-post"

    def test_preserves_fragment(self):
        result = normalize_url("https://example.com/post#section-2")
        assert result == "https://example.com/post#section-2"

    def test_preserves_path_and_fragment(self):
        result = normalize_url("https://example.com/docs/api#auth")
        assert result == "https://example.com/docs/api#auth"

    def test_preserves_non_tracking_query_params(self):
        result = normalize_url("https://example.com/search?q=python&page=3")
        # parse_qs may reorder params; check both are present
        assert "q=python" in result
        assert "page=3" in result
        assert result.startswith("https://example.com/search?")

    def test_strips_tracking_but_keeps_non_tracking(self):
        result = normalize_url(
            "https://example.com/search?q=python&utm_source=twitter&page=2"
        )
        assert "q=python" in result
        assert "page=2" in result
        assert "utm_source" not in result


# --- Edge cases ---


class TestEdgeCases:
    def test_no_query_string(self):
        assert normalize_url("https://example.com/post") == "https://example.com/post"

    def test_empty_url_returns_empty(self):
        assert normalize_url("") == ""

    def test_url_with_only_tracking_params(self):
        result = normalize_url("https://example.com/post?utm_source=tw&fbclid=abc")
        assert result == "https://example.com/post"

    def test_preserves_port(self):
        result = normalize_url("https://example.com:8080/api")
        assert result == "https://example.com:8080/api"

    def test_strips_default_port_80(self):
        result = normalize_url("http://example.com:80/api")
        assert "80" not in result
        assert "/api" in result

    def test_strips_default_port_443(self):
        result = normalize_url("https://example.com:443/api")
        assert "443" not in result
        assert "/api" in result

    def test_combined_normalization(self):
        """www stripping + lowercase + trailing slash + tracking params."""
        url = "https://WWW.Example.Com/Blog/?utm_source=rss&ref=sidebar"
        result = normalize_url(url)
        assert result == "https://example.com/Blog"

    def test_fragment_preserved_with_tracking_stripped(self):
        url = "https://example.com/post?utm_campaign=winter#heading"
        result = normalize_url(url)
        assert result == "https://example.com/post#heading"
