"""Atomic, project-local storage for reviewed observation snapshots."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from promptdrift.errors import PromptDriftError
from promptdrift.models import Config, ObservationSnapshot, RegressionReport
from promptdrift.models.monitor import MonitorReport
from promptdrift.models.provenance import Provenance


def snapshot_directory(config_path: Path) -> Path:
    return config_path.parent / ".promptdrift" / "snapshots"


def snapshot_path(config_path: Path, run_id: str) -> Path:
    if not run_id or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", run_id):
        raise PromptDriftError("Invalid snapshot run ID.")
    return snapshot_directory(config_path) / f"{run_id}.json"


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def configuration_hash(config: Config) -> str:
    return _digest(config.model_dump(mode="json"))


def provenance_hash(provenance: dict[str, Provenance | None]) -> str:
    comparable = {
        test_id: (
            {
                key: value
                for key, value in item.model_dump(mode="json").items()
                if key not in {"response_model_hash", "system_fingerprint_hash"}
            }
            if item is not None
            else None
        )
        for test_id, item in sorted(provenance.items())
    }
    return _digest(comparable)


def _snapshot_cases(report: MonitorReport | RegressionReport) -> list[dict[str, Any]]:
    if isinstance(report, MonitorReport):
        return [
            {
                "test_id": case.test_id,
                "status": case.status,
                "output_hash": case.output_hash,
                "assertions": case.assertions,
                "metrics": case.metrics,
                "provenance": case.provenance,
            }
            for case in report.tests
        ]
    return [
        {
            "test_id": case.test_id,
            "status": case.status,
            "output_hash": hashlib.sha256(case.output.encode("utf-8")).hexdigest(),
            "assertions": {result.assertion: result.passed for result in case.evaluations},
            "metrics": {
                "latency_ms": case.latency_ms,
                "input_tokens": case.input_tokens,
                "output_tokens": case.output_tokens,
                "estimated_cost_usd": case.estimated_cost_usd,
            },
            "provenance": case.provenance,
        }
        for case in report.tests
    ]


def snapshot_from_report(
    report: MonitorReport | RegressionReport,
    config: Config,
    expected_case_ids: list[str],
    *,
    source: str,
) -> ObservationSnapshot:
    expected_ids = set(expected_case_ids)
    cases = [case for case in _snapshot_cases(report) if case["test_id"] in expected_ids]
    case_provenance = {case["test_id"]: case["provenance"] for case in cases}
    return ObservationSnapshot(
        run_id=report.run_id,
        generated_at=report.generated_at,
        source=source,
        provider=report.provider,
        model=report.model,
        configuration_hash=configuration_hash(config),
        provenance_hash=provenance_hash(case_provenance),
        complete={case["test_id"] for case in cases} == expected_ids,
        expected_case_ids=sorted(expected_case_ids),
        tests=cases,
    )


def save_snapshot(snapshot: ObservationSnapshot, config_path: Path) -> Path:
    path = snapshot_path(config_path, snapshot.run_id)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(snapshot.model_dump_json(indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        return path
    except OSError as exc:
        raise PromptDriftError(f"Unable to save observation snapshot '{path.name}'.") from exc
    finally:
        temporary.unlink(missing_ok=True)


def load_snapshot(config_path: Path, run_id: str) -> ObservationSnapshot:
    path = snapshot_path(config_path, run_id)
    if not path.is_file():
        raise PromptDriftError(f"Reviewed observation snapshot not found: {path}")
    try:
        return ObservationSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, ValidationError, TypeError) as exc:
        raise PromptDriftError(
            f"Reviewed observation snapshot '{path.name}' is corrupt or incompatible."
        ) from exc
