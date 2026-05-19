"""Tests for readpile.cli.init — config generation."""

from pathlib import Path
from unittest.mock import patch

import pytest

from readpile.cli.init import _CONFIG_TEMPLATE


_FMT_KWARGS = dict(output_dir="~/readpile-output", auto_archive="false", whisper_model="medium")


class TestConfigTemplate:
    def test_template_has_auto_archive(self):
        rendered = _CONFIG_TEMPLATE.format(**_FMT_KWARGS)
        assert "auto_archive = false" in rendered

    def test_template_no_summarize_sections(self):
        rendered = _CONFIG_TEMPLATE.format(**_FMT_KWARGS)
        assert "[summarize]" not in rendered

    def test_template_has_required_sections(self):
        rendered = _CONFIG_TEMPLATE.format(**_FMT_KWARGS)
        assert "[general]" in rendered
        assert "[transcribe]" in rendered
        assert "[scrape]" in rendered
        assert "[crawl]" in rendered

    def test_auto_archive_true(self):
        rendered = _CONFIG_TEMPLATE.format(output_dir="~/my-output", auto_archive="true", whisper_model="medium")
        assert "auto_archive = true" in rendered
        assert 'output_dir = "~/my-output"' in rendered

    def test_whisper_model_in_template(self):
        rendered = _CONFIG_TEMPLATE.format(output_dir="~/out", auto_archive="false", whisper_model="large")
        assert 'whisper_model = "large"' in rendered
