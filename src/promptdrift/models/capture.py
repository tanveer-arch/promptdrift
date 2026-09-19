"""Domain models for interaction capture, scenario discovery, and suggestions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from promptdrift.models.test import Assertion, Threshold


class Interaction(BaseModel):
    """Raw captured model interaction (stored locally only)."""

    model_config = ConfigDict(extra="forbid")
    id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    provider: str
    model: str
    prompt: str
    system_prompt: str | None = None
    input: str
    variables: dict[str, Any] = Field(default_factory=dict)
    output: str
    latency_ms: float = 0.0
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None
    tags: list[str] = Field(default_factory=list)
    source: Literal["capture", "manual", "import", "generated"] = "capture"


class Scenario(BaseModel):
    """Scenario candidate or promoted regression case."""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    prompt: str | None = None  # Optional prompt file/template reference
    input: str
    variables: dict[str, Any] = Field(default_factory=dict)
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    source: Literal["capture", "manual", "import", "generated"] = "capture"
    status: Literal["candidate", "promoted", "ignored"] = "candidate"
    assertions: list[Assertion] = Field(default_factory=list)
    thresholds: dict[Literal["latency_ms", "cost_usd"], Threshold | float] = Field(
        default_factory=dict
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ScenarioLibrary(BaseModel):
    """Container for versioned scenarios."""

    model_config = ConfigDict(extra="forbid")
    version: int = 1
    scenarios: list[Scenario] = Field(default_factory=list)
