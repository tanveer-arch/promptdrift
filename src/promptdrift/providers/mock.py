"""Deterministic local provider for examples, tests, and offline onboarding."""
from __future__ import annotations

import re
import time

from promptdrift.models.result import ModelResponse

from .base import Provider


class MockProvider(Provider):
    def __init__(self, config):
        self.config = config

    def complete(self, prompt: str, *, temperature: float, max_output_tokens: int) -> ModelResponse:
        start = time.perf_counter()
        # The mock echoes explicit template values, making init usable without a network.
        output = re.sub(r"\s+", " ", prompt).strip()
        output = output[:max_output_tokens * 4]
        return ModelResponse(
            output=output,
            input_tokens=max(1, len(prompt.split())),
            output_tokens=max(1, len(output.split())),
            latency_ms=round((time.perf_counter() - start) * 1000, 3),
            model=self.config.model,
            provider="mock",
            estimated_cost_usd=0.0,
        )
