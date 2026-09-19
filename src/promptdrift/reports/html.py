"""Offline, dependency-free HTML report supporting regression reports and impact radius."""

from __future__ import annotations

import html
from pathlib import Path

from promptdrift.impact import ImpactRadiusReport
from promptdrift.models import RegressionReport

_STATUS_COLORS = {
    "PASS": "#22c55e",
    "WARN": "#eab308",
    "FAIL": "#ef4444",
    "REGRESSED": "#ef4444",
    "IMPROVED": "#22c55e",
    "UNCHANGED": "#6b7280",
    "CHANGED_BUT_VALID": "#eab308",
    "NEW": "#3b82f6",
    "MISSING": "#a855f7",
}


def write_html_report(
    report: RegressionReport,
    path: Path,
    impact: ImpactRadiusReport | None = None,
) -> None:
    counts = report.counts

    if impact:
        summary_html = f"""
        <div class="summary">
          <div class="stat pass"><strong>{impact.improved}</strong> improved</div>
          <div class="stat unchanged"><strong>{impact.unchanged}</strong> unchanged</div>
          <div class="stat warn"><strong>{impact.changed_but_valid}</strong> changed but valid</div>
          <div class="stat fail"><strong>{impact.regressed}</strong> regressed</div>
        </div>
        <div class="meta" style="margin-bottom: 1rem;">
          Impact Radius: <strong>{impact.impact_radius_percentage}%</strong> &middot; Latency Change: <strong>{impact.latency_pct_change:+.1f}%</strong> &middot; Cost Change: <strong>{impact.cost_pct_change:+.1f}%</strong>
        </div>
        """
        rows = ""
        for s in impact.scenarios:
            color = _STATUS_COLORS.get(s.classification, "#888")
            rows += (
                f"<tr>"
                f"<td>{html.escape(s.scenario_id)}</td>"
                f'<td style="color:{color};font-weight:600">{s.classification}</td>'
                f"<td>{html.escape(s.details)}</td>"
                f"<td>{s.latency_delta_ms:+.0f}ms</td>"
                f"</tr>\n"
            )
        table_headers = "<tr><th>Scenario</th><th>Classification</th><th>Details</th><th>Latency Delta</th></tr>"
    else:
        summary_html = f"""
        <div class="summary">
          <div class="stat pass"><strong>{counts["PASS"]}</strong> passed</div>
          <div class="stat warn"><strong>{counts["WARN"]}</strong> warnings</div>
          <div class="stat fail"><strong>{counts["FAIL"]}</strong> failed</div>
        </div>
        """
        rows = ""
        for test in report.tests:
            failed = next((x for x in test.evaluations if not x.passed), None)
            reason = html.escape(failed.reason if failed else "All assertions passed")
            color = _STATUS_COLORS.get(test.status, "#888")
            rows += (
                f"<tr>"
                f"<td>{html.escape(test.test_id)}</td>"
                f'<td style="color:{color};font-weight:600">{test.status}</td>'
                f"<td>{reason}</td>"
                f"<td>{test.latency_ms:.0f}ms</td>"
                f"</tr>\n"
            )
        table_headers = "<tr><th>Test</th><th>Status</th><th>Reason</th><th>Latency</th></tr>"

    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PromptDrift Report</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
    max-width: 960px;
    margin: 2rem auto;
    padding: 0 1rem;
    color: #1a1a2e;
    background: #fafafa;
  }}
  h1 {{ font-size: 1.5rem; margin-bottom: 0.5rem; }}
  .meta {{ color: #666; font-size: 0.875rem; margin-bottom: 1.5rem; }}
  .summary {{
    display: flex;
    gap: 1.5rem;
    margin-bottom: 1.5rem;
    flex-wrap: wrap;
  }}
  .stat {{
    padding: 0.75rem 1.25rem;
    border-radius: 8px;
    background: #fff;
    border: 1px solid #e5e7eb;
    font-size: 0.875rem;
  }}
  .stat strong {{ font-size: 1.25rem; display: block; }}
  .pass {{ border-left: 4px solid #22c55e; }}
  .unchanged {{ border-left: 4px solid #6b7280; }}
  .warn {{ border-left: 4px solid #eab308; }}
  .fail {{ border-left: 4px solid #ef4444; }}
  table {{
    border-collapse: collapse;
    width: 100%;
    background: #fff;
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid #e5e7eb;
  }}
  th {{
    background: #f9fafb;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #6b7280;
    padding: 0.75rem 1rem;
    text-align: left;
    border-bottom: 1px solid #e5e7eb;
  }}
  td {{
    padding: 0.75rem 1rem;
    border-bottom: 1px solid #f3f4f6;
    font-size: 0.875rem;
  }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover {{ background: #f9fafb; }}
</style>
</head>
<body>
<h1>PromptDrift Report</h1>
<p class="meta">{report.provider} / {html.escape(report.model)} &middot; {report.duration_ms:.0f}ms total</p>
{summary_html}
<table>
{table_headers}
{rows}</table>
</body>
</html>"""
    path.write_text(document, encoding="utf-8")
