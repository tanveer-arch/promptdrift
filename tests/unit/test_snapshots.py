"""Tests for reviewed observation snapshot storage and validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from promptdrift.errors import PromptDriftError
from promptdrift.models import Config, ObservationSnapshot, RegressionReport, TestRun
from promptdrift.models.provenance import Provenance
from promptdrift.storage.snapshots import (
    load_snapshot,
    save_snapshot,
    snapshot_from_report,
    snapshot_path,
)


def _snapshot() -> ObservationSnapshot:
    return ObservationSnapshot(
        run_id="reviewed-1",
        generated_at="2026-01-01T00:00:00Z",
        source="monitor",
        provider="mock",
        model="echo",
        configuration_hash="config-hash",
        provenance_hash="provenance-hash",
        complete=True,
        expected_case_ids=["greeting"],
        tests=[
            {
                "test_id": "greeting",
                "status": "PASS",
                "output_hash": "output-hash",
                "assertions": {"contains": True},
                "metrics": {"latency_ms": 1},
                "provenance": Provenance(
                    input_hash="input-hash",
                    configuration_hash="config-hash",
                    contract_hash="contract-hash",
                    provider_hash="provider-hash",
                    engine_version="0.4.0",
                ),
            }
        ],
    )


def test_snapshot_is_atomic_and_excludes_raw_content(tmp_path: Path):
    config_path = tmp_path / "promptdrift.yaml"
    snapshot = _snapshot()

    saved = save_snapshot(snapshot, config_path)

    assert saved == snapshot_path(config_path, "reviewed-1")
    content = saved.read_text(encoding="utf-8")
    assert "secret prompt" not in content
    assert "secret response" not in content
    assert not list(saved.parent.glob(f".{saved.name}.*"))
    assert load_snapshot(config_path, "reviewed-1").run_id == "reviewed-1"


def test_snapshot_projection_drops_regression_payloads():
    config = Config.model_validate(
        {
            "provider": {"type": "mock", "model": "echo"},
            "tests": [{"id": "case", "prompt": "prompt.txt"}],
        }
    )
    report = RegressionReport(
        provider="mock",
        model="echo",
        tests=[
            TestRun(
                test_id="case",
                provider="mock",
                model="echo",
                input="secret prompt",
                output="secret response",
                latency_ms=1,
            )
        ],
    )

    snapshot = snapshot_from_report(report, config, ["case"], source="check")
    serialized = snapshot.model_dump_json()

    assert "secret prompt" not in serialized
    assert "secret response" not in serialized


@pytest.mark.parametrize(
    "content",
    [
        "{",
        json.dumps({"schema_version": 1, "run_id": "partial"}),
        json.dumps({"schema_version": 99}),
    ],
)
def test_missing_corrupt_or_incompatible_snapshot_is_rejected(tmp_path: Path, content: str):
    config_path = tmp_path / "promptdrift.yaml"
    path = snapshot_path(config_path, "bad")
    path.parent.mkdir(parents=True)
    path.write_text(content, encoding="utf-8")

    with pytest.raises(PromptDriftError, match="corrupt or incompatible"):
        load_snapshot(config_path, "bad")


def test_missing_snapshot_is_rejected(tmp_path: Path):
    with pytest.raises(PromptDriftError, match="not found"):
        load_snapshot(tmp_path / "promptdrift.yaml", "missing")
