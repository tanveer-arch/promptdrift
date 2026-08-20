"""Tests for baseline regression comparison logic."""
import hashlib

from promptdrift.engine.regression import compare_to_baseline
from promptdrift.models import Baseline, BaselineTest, RegressionReport, TestRun


def make_baseline(tests_dict):
    return Baseline(
        schema_version=1,
        promptdrift_version="0.1.0",
        generated_at="2026-01-01T00:00:00Z",
        provider={"type": "mock", "model": "m"},
        tests=tests_dict,
    )


def make_report(*runs):
    return RegressionReport(provider="mock", model="m", tests=list(runs))


def make_run(test_id="x", output="test output", status="PASS"):
    return TestRun(
        test_id=test_id, provider="mock", model="m",
        input="prompt", output=output, latency_ms=1.0, status=status,
    )


def baseline_test(output="test output", status="PASS"):
    return BaselineTest(
        output_hash=hashlib.sha256(output.encode()).hexdigest(),
        status=status,
        assertions={},
        metrics={"latency_ms": 1.0, "input_tokens": None, "output_tokens": None, "estimated_cost_usd": None},
    )


class TestRegressionComparison:
    def test_identical_output_stays_pass(self):
        report = make_report(make_run(output="same"))
        baseline = make_baseline({"x": baseline_test(output="same")})
        result = compare_to_baseline(report, baseline)
        assert result.tests[0].status == "PASS"

    def test_changed_output_stays_pass_with_diagnostic(self):
        report = make_report(make_run(output="new output"))
        baseline = make_baseline({"x": baseline_test(output="old output")})
        result = compare_to_baseline(report, baseline)
        assert result.tests[0].status == "PASS"
        diagnostics = [e for e in result.tests[0].evaluations if e.assertion == "output_change"]
        assert len(diagnostics) == 1
        assert "changed" in diagnostics[0].reason.lower()

    def test_new_test_gets_warn(self):
        report = make_report(make_run(test_id="new_test"))
        baseline = make_baseline({})
        result = compare_to_baseline(report, baseline)
        assert result.tests[0].status == "WARN"
        has_baseline_eval = any(e.assertion == "baseline" for e in result.tests[0].evaluations)
        assert has_baseline_eval

    def test_failed_test_stays_failed(self):
        report = make_report(make_run(output="changed", status="FAIL"))
        baseline = make_baseline({"x": baseline_test(output="original")})
        result = compare_to_baseline(report, baseline)
        assert result.tests[0].status == "FAIL"

    def test_multiple_tests_compared_independently(self):
        report = make_report(
            make_run(test_id="a", output="same"),
            make_run(test_id="b", output="different"),
        )
        baseline = make_baseline({
            "a": baseline_test(output="same"),
            "b": baseline_test(output="original"),
        })
        result = compare_to_baseline(report, baseline)
        assert result.tests[0].status == "PASS"
        assert result.tests[1].status == "PASS"
        # Only test "b" should have output_change diagnostic
        a_diags = [e for e in result.tests[0].evaluations if e.assertion == "output_change"]
        b_diags = [e for e in result.tests[1].evaluations if e.assertion == "output_change"]
        assert len(a_diags) == 0
        assert len(b_diags) == 1

    def test_test_removed_from_config_is_ignored(self):
        """Baseline has tests that are no longer in the config — no error."""
        report = make_report(make_run(test_id="kept"))
        baseline = make_baseline({
            "kept": baseline_test(),
            "removed": baseline_test(),
        })
        result = compare_to_baseline(report, baseline)
        assert len(result.tests) == 1
        assert result.tests[0].test_id == "kept"

    def test_new_test_that_failed_stays_failed(self):
        report = make_report(make_run(test_id="brand_new", status="FAIL"))
        baseline = make_baseline({})
        result = compare_to_baseline(report, baseline)
        # FAIL should not be downgraded to WARN
        assert result.tests[0].status == "FAIL"
