from promptdrift.models import RegressionReport, TestRun
from promptdrift.reports.github import MARKER, github_markdown


def test_comment_is_marked_for_update():
    report = RegressionReport(provider="mock", model="m", tests=[TestRun(test_id="a", provider="mock", model="m", input="", output="", latency_ms=0)])
    assert MARKER in github_markdown(report)


def test_action_defers_failure_until_reports_are_written():
    manifest = open("action/action.yml", encoding="utf-8").read()
    assert "always() && inputs.upload-report" in manifest
    assert "Enforce PromptDrift result" in manifest
    assert "head.repo.fork == false" in manifest
