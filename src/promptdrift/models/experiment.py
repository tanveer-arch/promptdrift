"""Models for paired candidate-versus-control experiment runs with comparable provenance."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .config import ProviderConfig
from .provenance import Provenance
from .result import EvaluationResult


class ExperimentArmConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = "arm"
    provider: ProviderConfig
    temperature: float | None = None
    max_output_tokens: int | None = None
    system: str | None = None


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = "experiment"
    control: ExperimentArmConfig
    candidate: ExperimentArmConfig
    request_budget: int | None = Field(default=None, gt=0)
    max_output_characters: int = Field(default=20000, gt=0)


class PairedArmResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    arm: str
    test_id: str
    provider: str
    model: str
    output: str
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None
    provenance: Provenance | None = None
    evaluations: list[EvaluationResult] = Field(default_factory=list)
    status: Literal["PASS", "WARN", "FAIL", "ERROR"] = "PASS"
    error: str | None = None


class PairedScenarioComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: str
    input: str
    control: PairedArmResult
    candidate: PairedArmResult
    status: Literal["PASS", "WARN", "FAIL", "INCOMPARABLE"] = "PASS"
    latency_delta_ms: float | None = None
    cost_delta_usd: float | None = None
    token_delta: int | None = None
    assertion_changes: list[str] = Field(default_factory=list)


class ExperimentReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    experiment_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    control_arm: str
    candidate_arm: str
    pairs: list[PairedScenarioComparison] = Field(default_factory=list)
    total_pairs: int = 0
    passed_pairs: int = 0
    failed_pairs: int = 0
    incomparable_pairs: int = 0
    total_requests: int = 0
    duration_ms: float = 0.0
