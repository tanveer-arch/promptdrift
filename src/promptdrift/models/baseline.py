"""Git-friendly canonical baseline models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .provenance import Provenance


class BaselineDistribution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    samples: int = Field(ge=1)
    pass_rates: dict[str, float] = Field(default_factory=dict)
    assertion_counts: dict[str, dict[str, int]] = Field(default_factory=dict)
    output_hashes: list[str] = Field(default_factory=list)
    latency_p50_ms: float | None = None
    latency_p95_ms: float | None = None
    token_usage_avg: float | None = None


class BaselineTest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output_hash: str
    provenance: Provenance | None = None
    status: str
    assertions: dict[str, bool]
    metrics: dict[str, float | int | None]
    evaluator_scores: dict[str, float | None] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    distribution: BaselineDistribution | None = None


class Baseline(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1, 2, 3] = 3
    promptdrift_version: str
    generated_at: datetime
    provider: dict[str, str]
    prompt_revision: str | None = None
    git_sha: str | None = None
    prompt_hash: str | None = None
    tests: dict[str, BaselineTest]
