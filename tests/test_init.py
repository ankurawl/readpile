"""Tests for readpile.cli.init — config generation."""

from pathlib import Path
from unittest.mock import patch

import pytest

from readpile.cli.init import _CONFIG_TEMPLATE


_FMT_KWARGS = dict(whisper_model="medium", wiki_dir="~/my-wiki", hf_token="")


class TestConfigTemplate:
    def test_template_has_date_format(self):
        rendered = _CONFIG_TEMPLATE.format(**_FMT_KWARGS)
        assert 'date_format = "YYYY-MM-DD"' in rendered

    def test_template_has_filename_max_length(self):
        rendered = _CONFIG_TEMPLATE.format(**_FMT_KWARGS)
        assert "filename_max_length = 80" in rendered

    def test_template_no_summarize_sections(self):
        rendered = _CONFIG_TEMPLATE.format(**_FMT_KWARGS)
        assert "[summarize]" not in rendered

    def test_template_no_archive_fields(self):
        rendered = _CONFIG_TEMPLATE.format(**_FMT_KWARGS)
        assert "archive_dir" not in rendered
        assert "auto_archive" not in rendered

    def test_template_has_required_sections(self):
        rendered = _CONFIG_TEMPLATE.format(**_FMT_KWARGS)
        assert "[general]" in rendered
        assert "[transcribe]" in rendered
        assert "[scrape]" in rendered
        assert "[crawl]" in rendered
        assert "[wiki]" in rendered

    def test_whisper_model_in_template(self):
        rendered = _CONFIG_TEMPLATE.format(whisper_model="large", wiki_dir="~/my-wiki", hf_token="")
        assert 'whisper_model = "large"' in rendered
