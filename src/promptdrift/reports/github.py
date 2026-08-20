"""GitHub Step Summary and de-duplicatable PR-comment markdown."""
from promptdrift.models import RegressionReport

MARKER = "<!-- promptdrift-report -->"


def github_markdown(report: RegressionReport) -> str:
    counts = report.counts
    verdict = "❌ Regression detected" if counts["FAIL"] else ("⚠️ Warnings detected" if counts["WARN"] else "✅ All contracts passed")
    rows = []
    icons = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}
    for test in report.tests:
        failed = next((item for item in test.evaluations if not item.passed), None)
        rows.append(f"| {test.test_id} | {icons[test.status]} | {(failed.reason if failed else 'All assertions passed')} |")
    return "\n".join([MARKER, "## PromptDrift", "", verdict, "", "| Test | Status | Reason |", "|---|---|---|",
                        *rows, "", "### Summary", "", f"{counts['PASS']} passed · {counts['WARN']} warnings · {counts['FAIL']} failed", ""])
