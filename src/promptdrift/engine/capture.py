"""Interaction capture and proxy logging helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from promptdrift.models.capture import Interaction
from promptdrift.storage.sqlite import record_interaction


def create_interaction(
    provider: str,
    model: str,
    input: str,
    output: str,
    *,
    prompt: str = "prompts/example.txt",
    system_prompt: str | None = None,
    variables: dict[str, Any] | None = None,
    latency_ms: float = 0.0,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    estimated_cost_usd: float | None = None,
    tags: list[str] | None = None,
    source: str = "capture",
    interaction_id: str | None = None,
) -> Interaction:
    if not interaction_id:
        interaction_id = f"int_{uuid.uuid4().hex[:12]}"

    interaction = Interaction(
        id=interaction_id,
        timestamp=datetime.now(UTC),
        provider=provider,
        model=model,
        prompt=prompt,
        system_prompt=system_prompt,
        input=input,
        variables=variables or {},
        output=output,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=estimated_cost_usd,
        tags=tags or [],
        source=source,  # type: ignore
    )
    record_interaction(interaction)
    return interaction
