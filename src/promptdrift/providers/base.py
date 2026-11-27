"""Provider boundary used by the execution engine."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from promptdrift.models.result import ModelResponse, ToolCall


def normalize_tool_arguments(arguments: Any) -> dict[str, Any] | str:
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return arguments
        return parsed if isinstance(parsed, dict) else arguments
    try:
        return json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return repr(arguments)


def normalize_tool_call(value: Any) -> ToolCall | None:
    if not isinstance(value, dict):
        return None
    name = value.get("name")
    if not isinstance(name, str) or not name:
        return None
    return ToolCall(
        id=value.get("id") if isinstance(value.get("id"), str) else "",
        name=name,
        arguments=normalize_tool_arguments(value.get("arguments", {})),
    )


class Provider(ABC):
    @abstractmethod
    def complete(self, prompt: str, *, temperature: float, max_output_tokens: int) -> ModelResponse:
        """Return a normalized model response or raise ProviderError."""
