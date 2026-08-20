"""Strict, serializable configuration models."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .test import TestCase


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["openai", "ollama", "mock"]
    model: str = "mock"
    api_key_env: str | None = None
    base_url: str | None = None


class Defaults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    temperature: float = Field(default=0, ge=0, le=2)
    max_output_tokens: int = Field(default=500, gt=0)


class BaselineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = "promptdrift.baseline.json"
    store_raw_output: bool = False


class CIConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fail_on: list[Literal["assertion_failure", "latency_regression", "cost_regression"]] = [
        "assertion_failure"
    ]
    warn_on: list[Literal["semantic_change", "latency_regression", "cost_regression"]] = [
        "semantic_change", "latency_regression"
    ]


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1]
    provider: ProviderConfig
    defaults: Defaults = Field(default_factory=Defaults)
    baseline: BaselineConfig = Field(default_factory=BaselineConfig)
    ci: CIConfig = Field(default_factory=CIConfig)
    tests: list[TestCase] = Field(min_length=1)

    @field_validator("tests")
    @classmethod
    def test_ids_are_unique(cls, tests: list[TestCase]) -> list[TestCase]:
        ids = [test.id for test in tests]
        if len(ids) != len(set(ids)):
            raise ValueError("test ids must be unique")
        return tests

    def resolve_path(self, config_path: Path, value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else config_path.parent / path
