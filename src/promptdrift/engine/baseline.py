"""Read/write deterministic, Git-friendly baselines with v1/v2 schema compatibility."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from promptdrift import __version__
from promptdrift.errors import BaselineError
from promptdrift.models import (
    Baseline,
    BaselineDistribution,
    BaselineTest,
    RegressionReport,
    TestRun,
)


def calculate_wilson_interval(
    successes: int, total: int, confidence: float = 0.95
) -> tuple[float, float]:
    """Calculate the Wilson score confidence interval for a binomial proportion.

    Returns (lower_bound, upper_bound) rounded to 4 decimal places.
    """
    if total <= 0:
        return 0.0, 1.0
    if confidence >= 0.99:
        z = 2.5758
    elif confidence >= 0.95:
        z = 1.95996
    else:
        z = 1.6449

    p = successes / total
    z2 = z * z
    denominator = 1.0 + z2 / total
    center = (p + z2 / (2.0 * total)) / denominator
    margin = (z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * total)) / total)) / denominator
    lower = max(0.0, center - margin)
    upper = min(1.0, center + margin)
    return round(lower, 4), round(upper, 4)


def build_distribution(runs: list[TestRun]) -> BaselineDistribution:
    """Build empirical BaselineDistribution from multiple calibration test runs."""
    samples = len(runs)
    if not runs:
        return BaselineDistribution(samples=1)

    assertion_counts: dict[str, dict[str, int]] = {}
    output_hashes: list[str] = []
    latencies: list[float] = []
    total_tokens: list[int] = []

    for run in runs:
        output_hashes.append(hashlib.sha256(run.output.encode()).hexdigest())
        if run.latency_ms is not None:
            latencies.append(run.latency_ms)
        tokens = 0
        has_tokens = False
        if run.input_tokens is not None:
            tokens += run.input_tokens
            has_tokens = True
        if run.output_tokens is not None:
            tokens += run.output_tokens
            has_tokens = True
        if has_tokens:
            total_tokens.append(tokens)

        for ev in run.evaluations:
            counts = assertion_counts.setdefault(ev.assertion, {"pass": 0, "fail": 0})
            if ev.passed:
                counts["pass"] += 1
            else:
                counts["fail"] += 1

    pass_rates: dict[str, float] = {}
    for assertion_name, counts in sorted(assertion_counts.items()):
        total_evals = counts["pass"] + counts["fail"]
        pass_rates[assertion_name] = (
            round(counts["pass"] / total_evals, 4) if total_evals > 0 else 0.0
        )

    latencies.sort()
    latency_p50 = None
    latency_p95 = None
    if latencies:
        p50_idx = int(0.5 * len(latencies))
        p95_idx = min(len(latencies) - 1, int(0.95 * len(latencies)))
        latency_p50 = round(latencies[p50_idx], 2)
        latency_p95 = round(latencies[p95_idx], 2)

    token_avg = round(sum(total_tokens) / len(total_tokens), 2) if total_tokens else None
    unique_hashes = list(dict.fromkeys(output_hashes))

    return BaselineDistribution(
        samples=samples,
        pass_rates=pass_rates,
        assertion_counts=assertion_counts,
        output_hashes=unique_hashes,
        latency_p50_ms=latency_p50,
        latency_p95_ms=latency_p95,
        token_usage_avg=token_avg,
    )


def baseline_from_report(
    report: RegressionReport,
    prompt_revision: str | None = None,
    git_sha: str | None = None,
    prompt_hash: str | None = None,
    runs_by_test: dict[str, list[TestRun]] | None = None,
) -> Baseline:
    tests: dict[str, BaselineTest] = {}
    for run in report.tests:
        dist: BaselineDistribution | None = None
        if runs_by_test and run.test_id in runs_by_test and len(runs_by_test[run.test_id]) > 1:
            dist = build_distribution(runs_by_test[run.test_id])

        tests[run.test_id] = BaselineTest(
            output_hash=hashlib.sha256(run.output.encode()).hexdigest(),
            provenance=run.provenance,
            status=run.status,
            assertions={evaluation.assertion: evaluation.passed for evaluation in run.evaluations},
            metrics={
                "latency_ms": run.latency_ms,
                "input_tokens": run.input_tokens,
                "output_tokens": run.output_tokens,
                "estimated_cost_usd": run.estimated_cost_usd,
            },
            evaluator_scores={},
            metadata={},
            distribution=dist,
        )

    return Baseline(
        schema_version=3,
        promptdrift_version=__version__,
        generated_at=datetime.now(UTC),
        provider={"type": report.provider, "model": report.model},
        prompt_revision=prompt_revision,
        git_sha=git_sha,
        prompt_hash=prompt_hash,
        tests=tests,
    )


def write_baseline(
    path: Path,
    report: RegressionReport,
    *,
    force: bool = False,
    prompt_revision: str | None = None,
    git_sha: str | None = None,
    prompt_hash: str | None = None,
    runs_by_test: dict[str, list[TestRun]] | None = None,
) -> None:
    if path.exists() and not force:
        raise BaselineError(f"Baseline already exists: {path}. Use --force to replace it.")

    if path.is_file():
        from promptdrift.engine.baseline_history import archive_baseline

        archive_baseline(path)

    path.parent.mkdir(parents=True, exist_ok=True)
    baseline_obj = baseline_from_report(
        report,
        prompt_revision=prompt_revision,
        git_sha=git_sha,
        prompt_hash=prompt_hash,
        runs_by_test=runs_by_test,
    )
    content = baseline_obj.model_dump_json(indent=2) + "\n"
    atomic_write(path, content)


def load_baseline(path: Path) -> Baseline:
    if not path.is_file():
        raise BaselineError(f"Baseline file not found: {path}. Run 'promptdrift baseline' first.")
    try:
        raw_text = path.read_text(encoding="utf-8")
        data: dict[str, Any] = json.loads(raw_text)
        # Migrate schema_version 1 to schema_version 2 dynamically
        if data.get("schema_version") == 1:
            data["schema_version"] = 2
            for test_data in data.get("tests", {}).values():
                if "evaluator_scores" not in test_data:
                    test_data["evaluator_scores"] = {}
                if "metadata" not in test_data:
                    test_data["metadata"] = {}
        return Baseline.model_validate(data)
    except (ValidationError, json.JSONDecodeError, AttributeError, TypeError, OSError) as exc:
        raise BaselineError(
            f"Invalid baseline {path.name} or unreadable file ({type(exc).__name__})."
        ) from exc


def atomic_write(path: Path, content: str) -> None:
    """Keep the previous canonical file intact if serialization/writing is interrupted."""
    import os
    import tempfile

    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise BaselineError(
            f"Unable to write baseline {path.name} ({type(exc).__name__})."
        ) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
