"""Deterministic local provider for examples, tests, and offline onboarding."""

from __future__ import annotations

import json
import re
import time

from promptdrift.models.result import ModelResponse

from .base import Provider


class MockProvider(Provider):
    def __init__(self, config):
        self.config = config

    def complete(self, prompt: str, *, temperature: float, max_output_tokens: int) -> ModelResponse:
        start = time.perf_counter()
        tool_calls = []
        output_prompt = prompt
        try:
            payload = json.loads(prompt)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("tool_calls"), list):
            from .base import normalize_tool_call

            tool_calls = [
                call
                for item in payload["tool_calls"]
                for call in [normalize_tool_call(item)]
                if call is not None
            ]
            output_prompt = payload.get("output", "")
            if not isinstance(output_prompt, str):
                output_prompt = ""
        # The mock echoes explicit template values, making init usable without a network.
        output = re.sub(r"\s+", " ", output_prompt).strip()
        output = output[: max_output_tokens * 4]
        return ModelResponse(
            output=output,
            input_tokens=max(1, len(prompt.split())),
            output_tokens=max(1, len(output.split())),
            latency_ms=round((time.perf_counter() - start) * 1000, 3),
            model=self.config.model,
            provider="mock",
            estimated_cost_usd=0.0,
            tool_calls=tool_calls,
        )
