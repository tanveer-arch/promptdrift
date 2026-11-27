"""Provider boundary used by the execution engine."""

from __future__ import annotations

from abc import ABC, abstractmethod

from promptdrift.models.result import ModelResponse


class Provider(ABC):
    @abstractmethod
    def complete(self, prompt: str, *, temperature: float, max_output_tokens: int) -> ModelResponse:
        """Return a normalized model response or raise ProviderError."""

    async def acomplete(
        self, prompt: str, *, temperature: float, max_output_tokens: int
    ) -> ModelResponse:
        """Return a normalized model response asynchronously or raise ProviderError."""
        return self.complete(prompt, temperature=temperature, max_output_tokens=max_output_tokens)
