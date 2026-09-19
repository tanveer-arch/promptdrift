"""GitHub Step Summary and de-duplicatable PR-comment markdown."""

from __future__ import annotations

from promptdrift.impact import ImpactRadiusReport
from promptdrift.models import RegressionReport

MARKER = "<!-- promptdrift-report -->"


def github_markdown(report: RegressionReport, impact: ImpactRadiusReport | None = None) -> str:
    if impact is not None:
        return github_impact_markdown(impact)

    counts = report.counts
    verdict = (
        "❌ Regression detected"
        if counts["FAIL"]
        else ("⚠️ Warnings detected" if counts["WARN"] else "✅ All contracts passed")
    )
    rows = []
    icons = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}
    for test in report.tests:
        failed = next((item for item in test.evaluations if not item.passed), None)
        rows.append(
            f"| {test.test_id} | {icons.get(test.status, '❓')} | {(failed.reason if failed else 'All assertions passed')} |"
        )
    return "\n".join(
        [
            MARKER,
            "## PromptDrift",
            "",
            verdict,
            "",
            "| Test | Status | Reason |",
            "|---|---|---|",
            *rows,
            "",
            "### Summary",
            "",
            f"{counts['PASS']} passed · {counts['WARN']} warnings · {counts['FAIL']} failed",
            "",
        ]
    )


def github_impact_markdown(impact: ImpactRadiusReport) -> str:
    if impact.regressed > 0:
        verdict = f"⚠️ {impact.regressed} behavioral regression{'s' if impact.regressed > 1 else ''} detected"
    else:
        verdict = "✅ No behavioral regressions detected"

    table = [
        "| Metric | Total | Regressed | Improved | Latency Change | Cost Change |",
        "|---|---:|---:|---:|---:|---:|",
        f"| Scenarios | {impact.total_scenarios} | {impact.regressed} | {impact.improved} | {impact.latency_pct_change:+.1f}% | {impact.cost_pct_change:+.1f}% |",
    ]

    regressions = [s for s in impact.scenarios if s.classification == "REGRESSED"]
    reg_section = []
    if regressions:
        reg_section.append("### Regressions")
        for s in regressions:
            reg_section.append(f"- `{s.scenario_id}` — {s.details}")
        reg_section.append("")

    changed_valid = [s for s in impact.scenarios if s.classification == "CHANGED_BUT_VALID"]
    valid_section = []
    if changed_valid:
        valid_section.append("### Changed but valid")
        valid_section.append(
            f"{len(changed_valid)} scenarios changed wording but still satisfy all contracts."
        )
        valid_section.append("")

    return "\n".join(
        [
            MARKER,
            "## PromptDrift",
            "",
            verdict,
            "",
            *table,
            "",
            *reg_section,
            *valid_section,
        ]
    )
