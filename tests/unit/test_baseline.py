"""Tests for baseline read/write and safety guarantees."""

import pytest

from promptdrift.engine.baseline import load_baseline, write_baseline
from promptdrift.errors import BaselineError
from promptdrift.models import RegressionReport, TestRun
from promptdrift.models.result import EvaluationResult


def make_report(test_id="x", output="test output", status="PASS", evaluations=None):
    return RegressionReport(
        provider="mock",
        model="m",
        tests=[
            TestRun(
                test_id=test_id,
                provider="mock",
                model="m",
                input="prompt",
                output=output,
                latency_ms=1.0,
                input_tokens=3,
                output_tokens=2,
                estimated_cost_usd=0.001,
                evaluations=evaluations or [],
                status=status,
            )
        ],
    )


class TestBaselineRoundtrip:
    def test_write_and_load(self, tmp_path):
        path = tmp_path / "baseline.json"
        report = make_report()
        write_baseline(path, report)
        baseline = load_baseline(path)
        assert "x" in baseline.tests
        assert baseline.tests["x"].status == "PASS"

    def test_preserves_output_hash(self, tmp_path):
        import hashlib
        path = tmp_path / "baseline.json"
        report = make_report(output="deterministic")
        write_baseline(path, report)
        baseline = load_baseline(path)
        expected_hash = hashlib.sha256(b"deterministic").hexdigest()
        assert baseline.tests["x"].output_hash == expected_hash

    def test_preserves_assertion_results(self, tmp_path):
        path = tmp_path / "baseline.json"
        report = make_report(evaluations=[
            EvaluationResult(passed=True, assertion="contains", expected="test", actual="test output", reason="ok"),
            EvaluationResult(passed=False, assertion="max_length", expected=5, actual=11, reason="too long", severity="warn"),
        ])
        write_baseline(path, report)
        baseline = load_baseline(path)
        assert baseline.tests["x"].assertions["contains"] is True
        assert baseline.tests["x"].assertions["max_length"] is False

    def test_preserves_metrics(self, tmp_path):
        path = tmp_path / "baseline.json"
        write_baseline(path, make_report())
        baseline = load_baseline(path)
        metrics = baseline.tests["x"].metrics
        assert metrics["latency_ms"] == 1.0
        assert metrics["input_tokens"] == 3
        assert metrics["output_tokens"] == 2

    def test_multiple_tests(self, tmp_path):
        path = tmp_path / "baseline.json"
        report = RegressionReport(
            provider="mock", model="m",
            tests=[
                TestRun(test_id="a", provider="mock", model="m", input="p1", output="o1", latency_ms=1),
                TestRun(test_id="b", provider="mock", model="m", input="p2", output="o2", latency_ms=2),
            ],
        )
        write_baseline(path, report)
        baseline = load_baseline(path)
        assert len(baseline.tests) == 2
        assert "a" in baseline.tests
        assert "b" in baseline.tests


class TestBaselineSafety:
    def test_no_silent_overwrite(self, tmp_path):
        path = tmp_path / "baseline.json"
        write_baseline(path, make_report())
        with pytest.raises(BaselineError, match="already exists"):
            write_baseline(path, make_report())

    def test_force_overwrite(self, tmp_path):
        path = tmp_path / "baseline.json"
        write_baseline(path, make_report(output="first"))
        write_baseline(path, make_report(output="second"), force=True)
        baseline = load_baseline(path)
        import hashlib
        assert baseline.tests["x"].output_hash == hashlib.sha256(b"second").hexdigest()

    def test_creates_parent_directories(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "baseline.json"
        write_baseline(path, make_report())
        assert path.is_file()


class TestBaselineErrors:
    def test_missing_file(self, tmp_path):
        with pytest.raises(BaselineError, match="not found"):
            load_baseline(tmp_path / "nope.json")

    def test_corrupted_json(self, tmp_path):
        path = tmp_path / "baseline.json"
        path.write_text("{broken json", encoding="utf-8")
        with pytest.raises(BaselineError, match="Invalid baseline"):
            load_baseline(path)

    def test_invalid_schema(self, tmp_path):
        path = tmp_path / "baseline.json"
        path.write_text('{"not": "a baseline"}', encoding="utf-8")
        with pytest.raises(BaselineError, match="Invalid baseline"):
            load_baseline(path)
