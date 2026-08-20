"""Models representing declarative test contracts."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ASSERTION_TYPES = {
    "exact_match", "contains", "not_contains", "regex", "not_regex", "json_valid",
    "json_schema", "min_length", "max_length", "max_tokens", "latency_ms", "cost_usd",
}


class Assertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal[
        "exact_match", "contains", "not_contains", "regex", "not_regex", "json_valid",
        "json_schema", "min_length", "max_length", "max_tokens", "latency_ms", "cost_usd",
    ]
    value: Any | None = None
    schema_: dict[str, Any] | None = Field(default=None, alias="schema")
    name: str | None = None
    severity: Literal["fail", "warn"] = "fail"

    @model_validator(mode="after")
    def validate_payload(self) -> Assertion:
        if self.type == "json_schema" and not self.schema_:
            raise ValueError("json_schema assertions require a schema")
        if self.type not in {"json_valid", "json_schema"} and self.value is None:
            raise ValueError(f"{self.type} assertions require a value")
        return self

    @property
    def label(self) -> str:
        return self.name or self.type


class Evaluator(BaseModel):
    """Reserved model for a future explicit probabilistic evaluator extension."""
    model_config = ConfigDict(extra="forbid")
    type: Literal["semantic_similarity", "llm_judge", "similarity"]
    threshold: float | None = Field(default=None, ge=0, le=1)
    provider: str | None = None
    model: str | None = None


class OutputConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["text", "json"] = "text"


class Threshold(BaseModel):
    model_config = ConfigDict(extra="forbid")
    warn: float | None = Field(default=None, ge=0)
    fail: float | None = Field(default=None, ge=0)


class TestCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    prompt: str
    variables: dict[str, Any] = Field(default_factory=dict)
    assertions: list[Assertion] = Field(default_factory=list)
    evaluators: list[Evaluator] = Field(default_factory=list)
    output: OutputConfig = Field(default_factory=OutputConfig)
    thresholds: dict[Literal["latency_ms", "cost_usd"], Threshold | float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_unimplemented_evaluators(self) -> TestCase:
        if self.evaluators:
            raise ValueError(
                "optional evaluators are not available in PromptDrift 0.1.0; "
                "use deterministic assertions instead"
            )
        return self
