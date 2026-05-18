"""Tests for CLI restructuring — parent app regression tests."""

from typer.testing import CliRunner

from readpile.cli.main import app

runner = CliRunner()


class TestParentApp:
    def test_help_shows_init_and_wiki(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "init" in result.output
        assert "wiki" in result.output

    def test_init_help(self):
        result = runner.invoke(app, ["init", "--help"])
        assert result.exit_code == 0
        assert "config.toml" in result.output or "defaults" in result.output.lower()

    def test_wiki_help(self):
        result = runner.invoke(app, ["wiki", "--help"])
        assert result.exit_code == 0
        assert "init" in result.output
        assert "list" in result.output
        assert "search" in result.output
        assert "log" in result.output

    def test_wiki_init_help(self):
        result = runner.invoke(app, ["wiki", "init", "--help"])
        assert result.exit_code == 0
        assert "name" in result.output.lower()


class TestExistingImports:
    def test_config_template_importable(self):
        from readpile.cli.init import _CONFIG_TEMPLATE
        assert "[general]" in _CONFIG_TEMPLATE
