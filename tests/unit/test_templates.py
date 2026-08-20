"""Tests for Jinja2 prompt template rendering."""

import pytest

from promptdrift.errors import TemplateError
from promptdrift.templates import render_prompt


class TestTemplateRendering:
    def test_renders_single_variable(self, tmp_path):
        path = tmp_path / "prompt.txt"
        path.write_text("Hello {{ name }}")
        assert render_prompt(path, {"name": "Ada"}) == "Hello Ada"

    def test_renders_multiple_variables(self, tmp_path):
        path = tmp_path / "prompt.txt"
        path.write_text("{{ greeting }}, {{ name }}! You are {{ age }} years old.")
        result = render_prompt(path, {"greeting": "Hi", "name": "Bob", "age": "30"})
        assert result == "Hi, Bob! You are 30 years old."

    def test_renders_no_variables(self, tmp_path):
        path = tmp_path / "prompt.txt"
        path.write_text("No variables here.")
        assert render_prompt(path, {}) == "No variables here."

    def test_preserves_whitespace(self, tmp_path):
        path = tmp_path / "prompt.txt"
        path.write_text("Line 1\nLine 2\n  Indented")
        result = render_prompt(path, {})
        assert "Line 1\nLine 2\n  Indented" == result

    def test_handles_unicode(self, tmp_path):
        path = tmp_path / "prompt.txt"
        path.write_text("Translate: {{ text }}")
        result = render_prompt(path, {"text": "日本語のテスト"})
        assert "日本語のテスト" in result

    def test_handles_special_characters_in_value(self, tmp_path):
        path = tmp_path / "prompt.txt"
        path.write_text("Input: {{ data }}")
        result = render_prompt(path, {"data": '<script>alert("xss")</script>'})
        # SandboxedEnvironment with autoescape=False passes through raw content
        assert '<script>alert("xss")</script>' in result

    def test_extra_variables_ignored(self, tmp_path):
        path = tmp_path / "prompt.txt"
        path.write_text("Hello {{ name }}")
        result = render_prompt(path, {"name": "Ada", "extra": "ignored"})
        assert result == "Hello Ada"


class TestTemplateErrors:
    def test_missing_variable_raises_error(self, tmp_path):
        path = tmp_path / "prompt.txt"
        path.write_text("Hello {{ name }}")
        with pytest.raises(TemplateError, match="Missing"):
            render_prompt(path, {})

    def test_missing_one_of_many_variables(self, tmp_path):
        path = tmp_path / "prompt.txt"
        path.write_text("{{ a }} and {{ b }}")
        with pytest.raises(TemplateError, match="Missing"):
            render_prompt(path, {"a": "provided"})

    def test_missing_file_raises_error(self, tmp_path):
        path = tmp_path / "nonexistent.txt"
        with pytest.raises(TemplateError, match="not found"):
            render_prompt(path, {})

    def test_empty_template_renders_empty(self, tmp_path):
        path = tmp_path / "prompt.txt"
        path.write_text("")
        assert render_prompt(path, {}) == ""

    def test_jinja_syntax_error_raises_template_error(self, tmp_path):
        path = tmp_path / "prompt.txt"
        path.write_text("{% if unclosed %}")
        with pytest.raises(TemplateError):
            render_prompt(path, {})
