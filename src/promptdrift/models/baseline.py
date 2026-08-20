"""Git-friendly canonical baseline models."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BaselineTest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output_hash: str
    status: str
    assertions: dict[str, bool]
    metrics: dict[str, float | int | None]


class Baseline(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int = 1
    promptdrift_version: str
    generated_at: datetime
    provider: dict[str, str]
    tests: dict[str, BaselineTest]
