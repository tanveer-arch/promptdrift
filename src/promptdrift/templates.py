"""Safe deterministic Jinja prompt template rendering."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import StrictUndefined, meta
from jinja2.sandbox import SandboxedEnvironment

from .errors import TemplateError


def render_prompt(path: Path, variables: dict[str, Any]) -> str:
    if not path.is_file():
        raise TemplateError(f"Prompt file not found: {path}")
    source = path.read_text(encoding="utf-8")
    environment = SandboxedEnvironment(undefined=StrictUndefined, autoescape=False)
    try:
        parsed = environment.parse(source)
        missing = sorted(meta.find_undeclared_variables(parsed) - variables.keys())
        if missing:
            raise TemplateError("Missing prompt variables: " + ", ".join(missing))
        return environment.from_string(source).render(**variables)
    except TemplateError:
        raise
    except Exception as exc:
        raise TemplateError(f"Unable to render {path.name}: {exc}") from exc
