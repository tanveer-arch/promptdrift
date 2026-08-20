"""Read/write deterministic, Git-friendly baselines."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from promptdrift import __version__
from promptdrift.errors import BaselineError
from promptdrift.models import Baseline, BaselineTest, RegressionReport


def baseline_from_report(report: RegressionReport) -> Baseline:
    return Baseline(schema_version=1, promptdrift_version=__version__, generated_at=datetime.now(UTC),
        provider={"type": report.provider, "model": report.model}, tests={
            run.test_id: BaselineTest(output_hash=hashlib.sha256(run.output.encode()).hexdigest(), status=run.status,
                assertions={evaluation.assertion: evaluation.passed for evaluation in run.evaluations},
                metrics={"latency_ms": run.latency_ms, "input_tokens": run.input_tokens,
                         "output_tokens": run.output_tokens, "estimated_cost_usd": run.estimated_cost_usd})
            for run in report.tests})


def write_baseline(path: Path, report: RegressionReport, *, force: bool = False) -> None:
    if path.exists() and not force:
        raise BaselineError(f"Baseline already exists: {path}. Use --force to replace it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    content = baseline_from_report(report).model_dump_json(indent=2) + "\n"
    path.write_text(content, encoding="utf-8")


def load_baseline(path: Path) -> Baseline:
    if not path.is_file():
        raise BaselineError(f"Baseline file not found: {path}. Run 'promptdrift baseline' first.")
    try:
        return Baseline.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValidationError, json.JSONDecodeError) as exc:
        raise BaselineError(f"Invalid baseline {path.name}: {exc}") from exc
