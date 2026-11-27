"""Google Gemini GenerateContent API adapter without SDK coupling."""

from __future__ import annotations

import os
import time
from collections.abc import Callable

import httpx

from promptdrift.errors import ProviderAuthError, ProviderResponseError
from promptdrift.models.result import ModelResponse

from .base import Provider
from .resilience import ResilienceExecutor

GEMINI_DEFAULT_ENDPOINT = "https://generativelanguage.googleapis.com"


class GeminiProvider(Provider):
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
            provider_name="Gemini",
            clock=clock,
            sleeper=sleeper,
        )

    def complete(self, prompt: str, *, temperature: float, max_output_tokens: int) -> ModelResponse:
        env_name = self.config.api_key_env or "GEMINI_API_KEY"
        api_key = os.environ.get(env_name)
        if not api_key:
            raise ProviderAuthError(
                f"{env_name} is not set. Set it before using the Gemini provider."
            )
        start = self.executor.clock()

        def _attempt(timeout: float) -> ModelResponse:
            base = (self.config.base_url or GEMINI_DEFAULT_ENDPOINT).rstrip("/")
            url = f"{base}/v1beta/models/{self.config.model}:generateContent"

            generation_config: dict[str, int | float] = {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
            }

            body: dict = {
                "contents": [
                    {
                        "parts": [
                            {
                                "text": prompt,
                            }
                        ]
                    }
                ],
                "generationConfig": generation_config,
            }
            if self.config.system:
                body["systemInstruction"] = {"parts": [{"text": self.config.system}]}

            response = httpx.post(
                url,
                headers={
                    "x-goog-api-key": api_key,
                    "content-type": "application/json",
                },
                json=body,
                timeout=timeout,
            )
            response.raise_for_status()

            try:
                payload = response.json()
            except ValueError:
                raise ProviderResponseError("Gemini returned invalid JSON") from None

            if not isinstance(payload, dict):
                raise ProviderResponseError("Gemini response is not a JSON object")

            candidates = payload.get("candidates")
            if not isinstance(candidates, list) or not candidates:
                raise ProviderResponseError("Gemini response missing or empty candidates")

            candidate = candidates[0]
            if not isinstance(candidate, dict):
                raise ProviderResponseError("Gemini candidate is not a valid object")

            finish_reason = candidate.get("finishReason")
            if finish_reason in ("SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"):
                raise ProviderResponseError(
                    f"Gemini response blocked by safety filter: {finish_reason}"
                )

            content = candidate.get("content")
            if not isinstance(content, dict):
                raise ProviderResponseError("Gemini candidate missing content")

            parts = content.get("parts")
            if not isinstance(parts, list) or not parts:
                raise ProviderResponseError("Gemini content missing or empty parts")

            texts: list[str] = []
            for part in parts:
                if not isinstance(part, dict) or "text" not in part:
                    raise ProviderResponseError("Gemini part missing text")
                text = part["text"]
                if not isinstance(text, str):
                    raise ProviderResponseError("Gemini part text is not a string")
                texts.append(text)

            output = "".join(texts)
            usage = (
                payload.get("usageMetadata")
                if isinstance(payload.get("usageMetadata"), dict)
                else {}
            )

            input_tokens = usage.get("promptTokenCount")
            output_tokens = usage.get("candidatesTokenCount")

            return ModelResponse(
                output=output,
                input_tokens=input_tokens if isinstance(input_tokens, int) else None,
                output_tokens=output_tokens if isinstance(output_tokens, int) else None,
                latency_ms=round((self.executor.clock() - start) * 1000, 2),
                model=self.config.model,
                provider="gemini",
                resolved_model=payload.get("modelVersion"),
                system_fingerprint=None,
                estimated_cost_usd=None,
            )

        res = self.executor.execute(_attempt, start_time=start)
        res.latency_ms = round((self.executor.clock() - start) * 1000, 2)
        return res
