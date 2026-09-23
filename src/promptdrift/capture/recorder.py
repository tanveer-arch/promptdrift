"""Provider-agnostic interaction recorder with fail-safe boundary.

CaptureRecorder is the single entry point for all production capture.
Provider integrations (OpenAI, etc.) call this same recorder.
All exceptions are swallowed at the boundary — capture must never break the host app.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from promptdrift.capture.config import CaptureConfig
from promptdrift.models.capture import Interaction
from promptdrift.storage.sqlite import (
    count_interactions,
    purge_old_interactions,
    purge_oldest_interactions,
    record_interaction,
)


def _interaction_fingerprint(
    provider: str, model: str, prompt: str, input_text: str, variables: dict[str, Any] | None
) -> str:
    """Deterministic fingerprint for sampling decisions.

    Uses only stable identity fields so the same logical interaction
    at different times always produces the same sampling decision.
    """
    import json as _json

    normalized_input = " ".join(input_text.split()).strip().lower()
    canonical_vars = _json.dumps(variables or {}, sort_keys=True, default=str)
    raw = f"{provider}\x00{model}\x00{prompt}\x00{normalized_input}\x00{canonical_vars}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class CaptureRecorder:
    """Provider-agnostic interaction recorder.

    All public methods swallow exceptions so capture failures never
    propagate to the host application.
    """

    def __init__(self, config: CaptureConfig | None = None) -> None:
        self._config = config or CaptureConfig()

    @property
    def config(self) -> CaptureConfig:
        return self._config

    def record(
        self,
        *,
        prompt: str,
        input_text: str,
        output: str,
        model: str,
        provider: str,
        system_prompt: str | None = None,
        latency_ms: float = 0.0,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        estimated_cost_usd: float | None = None,
        tags: list[str] | None = None,
        variables: dict[str, Any] | None = None,
    ) -> Interaction | None:
        """Record a production interaction. Returns the Interaction or None.

        This method NEVER raises. All failures are silently swallowed.
        """
        try:
            return self._record_inner(
                prompt=prompt,
                input_text=input_text,
                output=output,
                model=model,
                provider=provider,
                system_prompt=system_prompt,
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost_usd=estimated_cost_usd,
                tags=tags,
                variables=variables,
            )
        except Exception:
            return None

    def _record_inner(
        self,
        *,
        prompt: str,
        input_text: str,
        output: str,
        model: str,
        provider: str,
        system_prompt: str | None,
        latency_ms: float,
        input_tokens: int | None,
        output_tokens: int | None,
        estimated_cost_usd: float | None,
        tags: list[str] | None,
        variables: dict[str, Any] | None,
    ) -> Interaction | None:
        cfg = self._config

        # Gate 1: opt-in check
        if not cfg.enabled:
            return None

        # Gate 2: deterministic sampling
        now = datetime.now(UTC)
        fingerprint = _interaction_fingerprint(provider, model, prompt, input_text, variables)

        from promptdrift.capture.sampling import should_sample

        if not should_sample(fingerprint, cfg.sample_rate):
            return None

        # Gate 3: apply redaction
        from promptdrift.capture.redaction import apply_redaction

        redacted_input = apply_redaction(input_text, cfg.redact_patterns, cfg.redact_callback)
        redacted_output = apply_redaction(output, cfg.redact_patterns, cfg.redact_callback)
        redacted_system = (
            apply_redaction(system_prompt, cfg.redact_patterns, cfg.redact_callback)
            if system_prompt
            else None
        )

        # Build interaction
        merged_tags = list(cfg.default_tags) + (tags or [])
        interaction_id = f"int_{uuid.uuid4().hex[:12]}"

        interaction = Interaction(
            id=interaction_id,
            timestamp=now,
            provider=provider,
            model=model,
            prompt=prompt,
            system_prompt=redacted_system,
            input=redacted_input,
            variables=variables or {},
            output=redacted_output,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=estimated_cost_usd,
            tags=merged_tags,
            source="capture",
        )

        # Store
        record_interaction(interaction, path=cfg.db_path)

        # Rolling retention: evict oldest if over cap
        if cfg.max_interactions is not None:
            current_count = count_interactions(path=cfg.db_path)
            if current_count > cfg.max_interactions:
                excess = current_count - cfg.max_interactions
                purge_oldest_interactions(excess, path=cfg.db_path)

        # Time-based retention
        if cfg.retention_days is not None:
            purge_old_interactions(cfg.retention_days, path=cfg.db_path)

        return interaction
