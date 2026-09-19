"""Impact radius engine and before/after behavior classification."""

from __future__ import annotations

import hashlib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from promptdrift.models.baseline import Baseline
from promptdrift.models.result import RegressionReport, TestRun

ChangeClassification = Literal[
    "REGRESSED",
    "IMPROVED",
    "UNCHANGED",
    "CHANGED_BUT_VALID",
    "NEW",
    "MISSING",
    "NOT_EVALUATED",
]


class ScenarioImpact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: str
    classification: ChangeClassification
    prompt: str | None = None
    category: str | None = None
    baseline_status: str | None = None
    current_status: str
    output_changed: bool
    latency_delta_ms: float = 0.0
    cost_delta_usd: float = 0.0
    details: str = ""


class ImpactRadiusReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total_scenarios: int
    regressed: int
    improved: int
    unchanged: int
    changed_but_valid: int
    new_scenarios: int
    missing_scenarios: int
    not_evaluated: int = 0
    impact_radius_percentage: float
    latency_pct_change: float = 0.0
    cost_pct_change: float = 0.0
    input_tokens_pct_change: float = 0.0
    output_tokens_pct_change: float = 0.0
    category_breakdown: dict[str, int] = Field(default_factory=dict)
    scenarios: list[ScenarioImpact] = Field(default_factory=list)


def classify_scenario_change(
    current_run: TestRun,
    baseline: Baseline | None,
    scenario_category: str | None = None,
    prompt: str | None = None,
) -> ScenarioImpact:
    if baseline is None:
        return ScenarioImpact(
            scenario_id=current_run.test_id,
            classification="NEW",
            prompt=prompt,
            category=scenario_category,
            current_status=current_run.status,
            output_changed=False,
            details="No baseline found for comparison.",
        )

    base_test = baseline.tests.get(current_run.test_id)
    if base_test is None:
        return ScenarioImpact(
            scenario_id=current_run.test_id,
            classification="NEW",
            prompt=prompt,
            category=scenario_category,
            current_status=current_run.status,
            output_changed=True,
            details="New scenario not present in baseline.",
        )

    curr_hash = hashlib.sha256(current_run.output.encode()).hexdigest()
    output_changed = curr_hash != base_test.output_hash

    base_lat = base_test.metrics.get("latency_ms") or 0.0
    curr_lat = current_run.latency_ms
    latency_delta = float(curr_lat) - float(base_lat)

    base_cost = base_test.metrics.get("estimated_cost_usd") or 0.0
    curr_cost = current_run.estimated_cost_usd or 0.0
    cost_delta = float(curr_cost) - float(base_cost)

    # Regressed: baseline was PASS/WARN, now FAIL
    if base_test.status in ("PASS", "WARN") and current_run.status == "FAIL":
        classification: ChangeClassification = "REGRESSED"
        failed_eval = next(
            (e for e in current_run.evaluations if not e.passed and e.severity == "fail"), None
        )
        details = failed_eval.reason if failed_eval else "Contract assertion failed."
    # Improved: baseline was FAIL, now PASS
    elif base_test.status == "FAIL" and current_run.status in ("PASS", "WARN"):
        classification = "IMPROVED"
        details = "Previously failing contract now passes."
    # Both fail or both pass
    elif current_run.status == "FAIL":
        classification = "REGRESSED"
        failed_eval = next(
            (e for e in current_run.evaluations if not e.passed and e.severity == "fail"), None
        )
        details = failed_eval.reason if failed_eval else "Contract assertion failed."
    else:
        # Both PASS/WARN
        if output_changed:
            classification = "CHANGED_BUT_VALID"
            details = "Output wording changed but all contracts still pass."
        else:
            classification = "UNCHANGED"
            details = "Behavior and output identical to baseline."

    return ScenarioImpact(
        scenario_id=current_run.test_id,
        classification=classification,
        prompt=prompt,
        category=scenario_category,
        baseline_status=base_test.status,
        current_status=current_run.status,
        output_changed=output_changed,
        latency_delta_ms=round(latency_delta, 2),
        cost_delta_usd=round(cost_delta, 6),
        details=details,
    )


def calculate_impact_radius(
    report: RegressionReport,
    baseline: Baseline | None,
    scenario_metadata: dict[str, dict[str, Any]] | None = None,
    skipped_ids: set[str] | None = None,
) -> ImpactRadiusReport:
    scenario_metadata = scenario_metadata or {}
    skipped_ids = skipped_ids or set()
    scenarios: list[ScenarioImpact] = []

    current_ids = {t.test_id for t in report.tests}
    category_breakdown: dict[str, int] = {}

    for run in report.tests:
        meta = scenario_metadata.get(run.test_id, {})
        category = meta.get("category", "general")
        prompt = meta.get("prompt")

        impact = classify_scenario_change(run, baseline, scenario_category=category, prompt=prompt)
        scenarios.append(impact)

        if impact.classification in ("REGRESSED", "IMPROVED", "CHANGED_BUT_VALID"):
            category_breakdown[category] = category_breakdown.get(category, 0) + 1

    # Check for missing or skipped scenarios in baseline
    if baseline:
        for base_id, base_test in baseline.tests.items():
            if base_id not in current_ids:
                if base_id in skipped_ids:
                    scenarios.append(
                        ScenarioImpact(
                            scenario_id=base_id,
                            classification="NOT_EVALUATED",
                            baseline_status=base_test.status,
                            current_status="NOT_EVALUATED",
                            output_changed=False,
                            details="Unaffected by this change; not re-evaluated.",
                        )
                    )
                else:
                    scenarios.append(
                        ScenarioImpact(
                            scenario_id=base_id,
                            classification="MISSING",
                            baseline_status=base_test.status,
                            current_status="MISSING",
                            output_changed=True,
                            details="Scenario present in baseline was omitted or deleted.",
                        )
                    )

    counts = {
        "REGRESSED": sum(1 for s in scenarios if s.classification == "REGRESSED"),
        "IMPROVED": sum(1 for s in scenarios if s.classification == "IMPROVED"),
        "UNCHANGED": sum(1 for s in scenarios if s.classification == "UNCHANGED"),
        "CHANGED_BUT_VALID": sum(1 for s in scenarios if s.classification == "CHANGED_BUT_VALID"),
        "NEW": sum(1 for s in scenarios if s.classification == "NEW"),
        "MISSING": sum(1 for s in scenarios if s.classification == "MISSING"),
        "NOT_EVALUATED": sum(1 for s in scenarios if s.classification == "NOT_EVALUATED"),
    }

    total = len(scenarios)
    evaluated_total = total - counts["NOT_EVALUATED"]
    affected = counts["REGRESSED"] + counts["IMPROVED"] + counts["CHANGED_BUT_VALID"]
    impact_pct = round((affected / evaluated_total) * 100, 1) if evaluated_total > 0 else 0.0

    # Calculate overall latency and cost deltas
    total_curr_lat = sum(r.latency_ms for r in report.tests)
    total_base_lat = 0.0
    total_curr_cost = sum(r.estimated_cost_usd or 0.0 for r in report.tests)
    total_base_cost = 0.0

    if baseline:
        for r in report.tests:
            b = baseline.tests.get(r.test_id)
            if b:
                total_base_lat += float(b.metrics.get("latency_ms") or 0.0)
                total_base_cost += float(b.metrics.get("estimated_cost_usd") or 0.0)

    lat_pct = (
        round(((total_curr_lat - total_base_lat) / total_base_lat) * 100, 1)
        if total_base_lat > 0
        else 0.0
    )
    cost_pct = (
        round(((total_curr_cost - total_base_cost) / total_base_cost) * 100, 1)
        if total_base_cost > 0
        else 0.0
    )

    return ImpactRadiusReport(
        total_scenarios=total,
        regressed=counts["REGRESSED"],
        improved=counts["IMPROVED"],
        unchanged=counts["UNCHANGED"],
        changed_but_valid=counts["CHANGED_BUT_VALID"],
        new_scenarios=counts["NEW"],
        missing_scenarios=counts["MISSING"],
        not_evaluated=counts["NOT_EVALUATED"],
        impact_radius_percentage=impact_pct,
        latency_pct_change=lat_pct,
        cost_pct_change=cost_pct,
        category_breakdown=category_breakdown,
        scenarios=scenarios,
    )
