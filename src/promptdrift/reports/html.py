"""Offline, dependency-free HTML report."""
from __future__ import annotations

import html
from pathlib import Path

from promptdrift.models import RegressionReport


def write_html_report(report: RegressionReport, path: Path) -> None:
    rows = "".join(f"<tr><td>{html.escape(test.test_id)}</td><td>{test.status}</td><td>{html.escape(next((x.reason for x in test.evaluations if not x.passed), 'All assertions passed'))}</td></tr>" for test in report.tests)
    counts = report.counts
    document = f"<!doctype html><meta charset=utf-8><title>PromptDrift report</title><style>body{{font-family:system-ui;max-width:1000px;margin:2rem auto}}table{{border-collapse:collapse;width:100%}}td,th{{padding:.6rem;border:1px solid #ddd;text-align:left}}</style><h1>PromptDrift</h1><p>{counts['PASS']} passed · {counts['WARN']} warnings · {counts['FAIL']} failed</p><table><tr><th>Test</th><th>Status</th><th>Reason</th></tr>{rows}</table>"
    path.write_text(document, encoding="utf-8")
