"""Anthropic Messages API adapter without SDK coupling."""

from __future__ import annotations

import os
import time
from collections.abc import Callable

import httpx

from promptdrift.errors import ProviderAuthError, ProviderResponseError
from promptdrift.models.result import ModelResponse

from .base import Provider
from .resilience import ResilienceExecutor

ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(Provider):
    def __init__(
        self,
        config,
        executor: ResilienceExecutor | None = None,
        clock: Callable[[], float] = time.perf_counter,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.config = config
        self.executor = executor or ResilienceExecutor(
            self.config.resilience,
            provider_name="Anthropic",
            clock=clock,
            sleeper=sleeper,
        )

    def complete(self, prompt: str, *, temperature: float, max_output_tokens: int) -> ModelResponse:
        env_name = self.config.api_key_env or "ANTHROPIC_API_KEY"
        api_key = os.environ.get(env_name)
        if not api_key:
            raise ProviderAuthError(
                f"{env_name} is not set. Set it before using the Anthropic provider."
            )
        start = self.executor.clock()

        def _attempt(timeout: float) -> ModelResponse:
            body = {
                "model": self.config.model,
                "max_tokens": max_output_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            }
            if self.config.system:
                body["system"] = self.config.system
            response = httpx.post(
                (self.config.base_url or "https://api.anthropic.com/v1").rstrip("/") + "/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json=body,
                timeout=timeout,
            )
            response.raise_for_status()
            try:
                payload = response.json()
            except ValueError:
                raise ProviderResponseError("Anthropic returned invalid JSON") from None
            blocks = payload.get("content") if isinstance(payload, dict) else None
            texts = [
                block["text"]
                for block in (blocks or [])
                if isinstance(block, dict)
                and block.get("type") == "text"
                and isinstance(block.get("text"), str)
            ]
            if not texts:
                raise ProviderResponseError("Anthropic response had no text content")
            usage = payload.get("usage") or {}
            return ModelResponse(
                output="".join(texts),
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                latency_ms=round((self.executor.clock() - start) * 1000, 2),
                model=self.config.model,
                provider="anthropic",
                resolved_model=payload.get("model"),
                system_fingerprint=None,
                estimated_cost_usd=None,
            )

        res = self.executor.execute(_attempt, start_time=start)
        res.latency_ms = round((self.executor.clock() - start) * 1000, 2)
        return res
