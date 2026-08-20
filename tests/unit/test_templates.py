from pathlib import Path

import pytest

from promptdrift.errors import TemplateError
from promptdrift.templates import render_prompt


def test_template_renders(tmp_path: Path):
    path = tmp_path / "prompt.txt"
    path.write_text("Hello {{ name }}")
    assert render_prompt(path, {"name": "Ada"}) == "Hello Ada"


def test_template_requires_variables(tmp_path: Path):
    path = tmp_path / "prompt.txt"
    path.write_text("Hello {{ name }}")
    with pytest.raises(TemplateError, match="Missing"):
        render_prompt(path, {})
