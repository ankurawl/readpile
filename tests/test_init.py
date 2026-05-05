"""Tests for mediakit.cli.init — config generation."""

from pathlib import Path
from unittest.mock import patch

import pytest

from mediakit.cli.init import _CONFIG_TEMPLATE


class TestConfigTemplate:
    def test_template_has_auto_archive(self):
        rendered = _CONFIG_TEMPLATE.format(output_dir="~/mediakit-output", auto_archive="false")
        assert "auto_archive = false" in rendered

    def test_template_no_summarize_sections(self):
        rendered = _CONFIG_TEMPLATE.format(output_dir="~/mediakit-output", auto_archive="false")
        assert "[summarize]" not in rendered
        assert "ollama" not in rendered
        assert "claude" not in rendered.split("[")[0] if "[" in rendered else True

    def test_template_has_required_sections(self):
        rendered = _CONFIG_TEMPLATE.format(output_dir="~/mediakit-output", auto_archive="false")
        assert "[general]" in rendered
        assert "[transcribe]" in rendered
        assert "[scrape]" in rendered
        assert "[crawl]" in rendered
        assert "[bot]" in rendered

    def test_auto_archive_true(self):
        rendered = _CONFIG_TEMPLATE.format(output_dir="~/my-output", auto_archive="true")
        assert "auto_archive = true" in rendered
        assert 'output_dir = "~/my-output"' in rendered
