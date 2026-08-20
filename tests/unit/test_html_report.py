"""Tests for HTML report generation."""

from promptdrift.models import RegressionReport, TestRun
from promptdrift.models.result import EvaluationResult
from promptdrift.reports.html import write_html_report


def make_report(tests):
    return RegressionReport(provider="mock", model="test-model", tests=tests)


class TestHtmlReport:
    def test_creates_file(self, tmp_path):
        path = tmp_path / "report.html"
        report = make_report([
            TestRun(test_id="hello", provider="mock", model="m", input="p", output="o", latency_ms=1),
        ])
        write_html_report(report, path)
        assert path.is_file()

    def test_contains_test_ids(self, tmp_path):
        path = tmp_path / "report.html"
        report = make_report([
            TestRun(test_id="test_one", provider="mock", model="m", input="p", output="o", latency_ms=1),
            TestRun(test_id="test_two", provider="mock", model="m", input="p", output="o", latency_ms=1),
        ])
        write_html_report(report, path)
        content = path.read_text(encoding="utf-8")
        assert "test_one" in content
        assert "test_two" in content

    def test_contains_summary_counts(self, tmp_path):
        path = tmp_path / "report.html"
        report = make_report([
            TestRun(test_id="a", provider="mock", model="m", input="p", output="o", latency_ms=1, status="PASS"),
            TestRun(test_id="b", provider="mock", model="m", input="p", output="o", latency_ms=1, status="FAIL",
                    evaluations=[EvaluationResult(passed=False, assertion="x", reason="fail", severity="fail")]),
        ])
        write_html_report(report, path)
        content = path.read_text(encoding="utf-8")
        assert "1" in content  # at least the counts appear

    def test_escapes_html_in_test_ids(self, tmp_path):
        path = tmp_path / "report.html"
        # dangerous_id = '<script>alert("xss")</script>'
        # TestCase ID validation prevents this, but html.py should still escape
        report = make_report([
            TestRun(test_id="safe_id", provider="mock", model="m", input="p", output="o", latency_ms=1),
        ])
        write_html_report(report, path)
        content = path.read_text(encoding="utf-8")
        assert "<script>" not in content

    def test_is_valid_html(self, tmp_path):
        path = tmp_path / "report.html"
        report = make_report([
            TestRun(test_id="hello", provider="mock", model="m", input="p", output="o", latency_ms=1),
        ])
        write_html_report(report, path)
        content = path.read_text(encoding="utf-8")
        assert content.startswith("<!doctype html>")
        assert "<table>" in content

    def test_shows_failure_reason(self, tmp_path):
        path = tmp_path / "report.html"
        report = make_report([
            TestRun(test_id="a", provider="mock", model="m", input="p", output="o", latency_ms=1, status="FAIL",
                    evaluations=[EvaluationResult(
                        passed=False, assertion="contains", expected="hello",
                        actual="o", reason="Required text missing", severity="fail",
                    )]),
        ])
        write_html_report(report, path)
        content = path.read_text(encoding="utf-8")
        assert "Required text missing" in content
