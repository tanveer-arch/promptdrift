"""Privacy-minimized reviewed observation snapshots."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .provenance import Provenance


class SnapshotCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_id: str
    status: Literal["PASS", "WARN", "FAIL", "ERROR"]
    output_hash: str | None = None
    assertions: dict[str, bool] = Field(default_factory=dict)
    metrics: dict[str, float | int | None] = Field(default_factory=dict)
    provenance: Provenance | None = None


class ObservationSnapshot(BaseModel):
    """The reviewed facts needed for provider-free baseline promotion.

    Raw prompts, responses, expected values, actual values, and evaluator
    explanations are deliberately not part of this model.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    run_id: str
    generated_at: datetime
    source: Literal["check", "monitor"]
    provider: str
    model: str
    configuration_hash: str
    provenance_hash: str
    complete: bool
    expected_case_ids: list[str]
    tests: list[SnapshotCase]
