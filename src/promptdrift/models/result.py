"""Normalized run and report results, independent of presentation."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float
    model: str
    provider: str
    estimated_cost_usd: float | None = None


class EvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    passed: bool
    assertion: str
    expected: Any = None
    actual: Any = None
    reason: str
    severity: Literal["fail", "warn"] = "fail"


class TestRun(BaseModel):
    __test__ = False
    model_config = ConfigDict(extra="forbid")
    test_id: str
    provider: str
    model: str
    input: str
    output: str
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None
    evaluations: list[EvaluationResult] = Field(default_factory=list)
    status: Literal["PASS", "WARN", "FAIL"] = "PASS"


class RegressionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    provider: str
    model: str
    tests: list[TestRun]
    baseline_path: str | None = None
    duration_ms: float = 0

    @property
    def counts(self) -> dict[str, int]:
        return {status: sum(test.status == status for test in self.tests) for status in ("PASS", "WARN", "FAIL")}
