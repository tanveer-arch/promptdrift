"""Unit tests for sampled reference distributions and statistical drift calibration."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from promptdrift.cli import app
from promptdrift.engine.baseline import build_distribution, calculate_wilson_interval
from promptdrift.engine.monitor import _diagnose
from promptdrift.models import (
    Baseline,
    BaselineDistribution,
    BaselineTest,
    EvaluationResult,
    TestRun,
)
from promptdrift.models.provenance import Provenance

runner = CliRunner()


def test_wilson_interval_boundaries():
    """Verify Wilson score confidence interval mathematical properties."""
    # Zero total returns [0.0, 1.0]
    assert calculate_wilson_interval(0, 0) == (0.0, 1.0)

    # 10/10 successes has high lower bound but not 1.0
    lower, upper = calculate_wilson_interval(10, 10, confidence=0.95)
    assert lower > 0.70
    assert upper == 1.0

    # 0/10 successes has low upper bound but not 0.0
    lower, upper = calculate_wilson_interval(0, 10, confidence=0.95)
    assert lower == 0.0
    assert upper < 0.30

    # 5/10 successes is centered at 0.5
    lower, upper = calculate_wilson_interval(5, 10, confidence=0.95)
    assert 0.20 < lower < 0.50
    assert 0.50 < upper < 0.80

    # Higher confidence widens the interval
    l90, u90 = calculate_wilson_interval(5, 10, confidence=0.90)
    l99, u99 = calculate_wilson_interval(5, 10, confidence=0.99)
    assert l99 < l90
    assert u99 > u90


def test_baseline_distribution_pydantic_schema():
    """Verify BaselineDistribution model serialization, validation and extra-forbid."""
    dist = BaselineDistribution(
        samples=5,
        pass_rates={"contains": 1.0, "max_length": 0.8},
        assertion_counts={
            "contains": {"pass": 5, "fail": 0},
            "max_length": {"pass": 4, "fail": 1},
        },
        output_hashes=["hash1", "hash2"],
        latency_p50_ms=120.5,
        latency_p95_ms=180.2,
        token_usage_avg=245.0,
    )

    data = dist.model_dump()
    assert data["samples"] == 5
    assert data["pass_rates"]["contains"] == 1.0
    assert len(data["output_hashes"]) == 2

    # Extra field is forbidden
    with pytest.raises(Exception):
        BaselineDistribution.model_validate({**data, "unexpected_extra": 123})

    # Backward compatibility: BaselineTest without distribution defaults to None
    test_obj = BaselineTest(
        output_hash="abc",
        status="PASS",
        assertions={"contains": True},
        metrics={"latency_ms": 100},
    )
    assert test_obj.distribution is None

    # Serialization roundtrip preserves distribution
    test_with_dist = BaselineTest(
        output_hash="abc",
        status="PASS",
        assertions={"contains": True},
        metrics={"latency_ms": 100},
        distribution=dist,
    )
    serialized = test_with_dist.model_dump_json()
    deserialized = BaselineTest.model_validate_json(serialized)
    assert deserialized.distribution is not None
    assert deserialized.distribution.samples == 5


def test_build_distribution_from_test_runs():
    """Verify empirical distribution aggregation across multi-sample test runs."""
    runs = [
        TestRun(
            test_id="test-1",
            provider="mock",
            model="local-echo",
            input="prompt 1",
            status="PASS",
            output="Refund within 30 days.",
            evaluations=[
                EvaluationResult(
                    passed=True,
                    assertion="contains",
                    expected="30 days",
                    actual="Refund within 30 days.",
                    reason="Required text found.",
                ),
                EvaluationResult(
                    passed=True,
                    assertion="max_length",
                    expected=100,
                    actual=24,
                    reason="Length within limit.",
                ),
            ],
            latency_ms=100.0,
            input_tokens=10,
            output_tokens=5,
        ),
        TestRun(
            test_id="test-1",
            provider="mock",
            model="local-echo",
            input="prompt 1",
            status="WARN",
            output="Returns accepted in 30 days guaranteed.",
            evaluations=[
                EvaluationResult(
                    passed=True,
                    assertion="contains",
                    expected="30 days",
                    actual="Returns accepted in 30 days guaranteed.",
                    reason="Required text found.",
                ),
                EvaluationResult(
                    passed=False,
                    assertion="max_length",
                    expected=30,
                    actual=40,
                    reason="Length exceeded limit.",
                ),
            ],
            latency_ms=200.0,
            input_tokens=12,
            output_tokens=8,
        ),
    ]

    dist = build_distribution(runs)
    assert dist.samples == 2
    assert dist.pass_rates["contains"] == 1.0
    assert dist.pass_rates["max_length"] == 0.5
    assert dist.assertion_counts["contains"] == {"pass": 2, "fail": 0}
    assert dist.assertion_counts["max_length"] == {"pass": 1, "fail": 1}
    assert len(dist.output_hashes) == 2
    assert dist.latency_p50_ms == 200.0
    assert dist.token_usage_avg == 17.5


def test_diagnose_with_calibrated_distribution_stationary():
    """A monitor probe within baseline Wilson CI variance should triage as stable."""
    prov = Provenance(
        input_hash="h_in",
        configuration_hash="h_conf",
        contract_hash="h_cont",
        provider_hash="h_prov",
        engine_version="0.4.0",
    )
    dist = BaselineDistribution(
        samples=10,
        pass_rates={"contains": 0.8},
        assertion_counts={"contains": {"pass": 8, "fail": 2}},
        output_hashes=["hash1", "hash2"],
    )
    old = BaselineTest(
        output_hash="hash1",
        provenance=prov,
        status="PASS",
        assertions={"contains": True},
        metrics={"latency_ms": 100},
        distribution=dist,
    )

    # 1 failure out of 3 samples = 66.7% pass rate.
    # 8/10 baseline pass rate gives Wilson 95% CI of ~[0.49, 0.94].
    # Since 66.7% is >= 49%, this is expected variance -> stable!
    diag, summary, evidence = _diagnose(
        old,
        prov,
        samples=3,
        failures=1,
        behavioral_failures=1,
        errors=0,
        changes=0,
        warnings=0,
        response_signals=set(),
    )
    assert diag == "stable"
    assert "within expected variance" in summary.lower()
    assert any("Calibrated reference distribution" in item for item in evidence)


def test_diagnose_with_calibrated_distribution_drift():
    """A monitor probe dropping below baseline Wilson CI lower bound should triage as drift."""
    prov = Provenance(
        input_hash="h_in",
        configuration_hash="h_conf",
        contract_hash="h_cont",
        provider_hash="h_prov",
        engine_version="0.4.0",
    )
    dist = BaselineDistribution(
        samples=10,
        pass_rates={"contains": 1.0},
        assertion_counts={"contains": {"pass": 10, "fail": 0}},
        output_hashes=["hash1"],
    )
    old = BaselineTest(
        output_hash="hash1",
        provenance=prov,
        status="PASS",
        assertions={"contains": True},
        metrics={"latency_ms": 100},
        distribution=dist,
    )

    # 3 failures out of 3 samples = 0.0% pass rate.
    # 10/10 baseline has lower bound > 70%. Probe pass rate (0%) < 70% -> observed_model_drift!
    diag, summary, evidence = _diagnose(
        old,
        prov,
        samples=3,
        failures=3,
        behavioral_failures=3,
        errors=0,
        changes=1,
        warnings=0,
        response_signals=set(),
    )
    assert diag == "observed_model_drift"
    assert any("dropped significantly below" in item.lower() for item in [summary] + evidence)


def test_diagnose_fallback_without_distribution():
    """When baseline lacks distribution (legacy), fall back to standard heuristic."""
    prov = Provenance(
        input_hash="h_in",
        configuration_hash="h_conf",
        contract_hash="h_cont",
        provider_hash="h_prov",
        engine_version="0.4.0",
    )
    old = BaselineTest(
        output_hash="hash1",
        provenance=prov,
        status="PASS",
        assertions={"contains": True},
        metrics={"latency_ms": 100},
        distribution=None,
    )

    # Without distribution, mixed pass/fail is stochastic_behavior
    diag, summary, _ = _diagnose(
        old,
        prov,
        samples=3,
        failures=1,
        behavioral_failures=1,
        errors=0,
        changes=0,
        warnings=0,
        response_signals=set(),
    )
    assert diag == "stochastic_behavior"


def test_cli_baseline_samples_flag(tmp_path: Path):
    """Verify promptdrift baseline --samples N generates calibrated distribution."""
    config_file = tmp_path / "promptdrift.yaml"
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("Hello world")

    config_content = f"""
version: 2
provider:
  type: mock
  model: local-echo
baseline:
  path: baseline.json
tests:
  - id: test-echo
    prompt: {prompt_file.name}
    assertions:
      - type: contains
        value: Hello
"""
    config_file.write_text(config_content)

    result = runner.invoke(
        app,
        ["baseline", "--config", str(config_file), "--samples", "3"],
    )
    assert result.exit_code == 0
    assert "Calibrated baseline written (3 samples)" in result.stdout

    baseline_path = tmp_path / "baseline.json"
    assert baseline_path.exists()
    baseline = Baseline.model_validate_json(baseline_path.read_text())
    assert baseline.tests["test-echo"].distribution is not None
    assert baseline.tests["test-echo"].distribution.samples == 3
    assert baseline.tests["test-echo"].distribution.pass_rates["contains"] == 1.0
