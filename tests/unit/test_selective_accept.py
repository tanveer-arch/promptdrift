"""Tests for selective acceptance."""

from __future__ import annotations

import pytest

from promptdrift.engine.accept import selective_accept
from promptdrift.errors import PromptDriftError
from promptdrift.impact import ImpactRadiusReport
from promptdrift.models.baseline import Baseline, BaselineTest
from promptdrift.models.result import RegressionReport, TestRun


class TestSelectiveAccept:
    @pytest.fixture
    def current_baseline(self):
        return Baseline(
            schema_version=2,
            promptdrift_version="0.1.0",
            generated_at="2024-01-01T00:00:00Z",
            provider={"type": "mock", "model": "test"},
            git_sha="old_sha",
            prompt_hash="old_prompt",
            tests={
                "t1": BaselineTest(output_hash="h1", status="pass", assertions={}, metrics={}),
                "t2": BaselineTest(output_hash="h2", status="pass", assertions={}, metrics={}),
                "t3": BaselineTest(output_hash="h3", status="pass", assertions={}, metrics={}),
            },
        )

    @pytest.fixture
    def new_report(self):
        return RegressionReport(
            provider="mock",
            model="test",
            tests=[
                TestRun(
                    test_id="t1",
                    provider="mock",
                    model="test",
                    input="in1",
                    output="new1",
                    status="PASS",
                    evaluations=[],
                    latency_ms=0,
                    input_tokens=0,
                    output_tokens=0,
                    estimated_cost_usd=0,
                ),
                TestRun(
                    test_id="t2",
                    provider="mock",
                    model="test",
                    input="in2",
                    output="new2",
                    status="PASS",
                    evaluations=[],
                    latency_ms=0,
                    input_tokens=0,
                    output_tokens=0,
                    estimated_cost_usd=0,
                ),
                TestRun(
                    test_id="t3",
                    provider="mock",
                    model="test",
                    input="in3",
                    output="new3",
                    status="PASS",
                    evaluations=[],
                    latency_ms=0,
                    input_tokens=0,
                    output_tokens=0,
                    estimated_cost_usd=0,
                ),
            ],
        )

    def test_rejects_regressions_by_default(self, current_baseline, new_report):
        from promptdrift.impact import ScenarioImpact

        impact = ImpactRadiusReport(
            total_scenarios=1,
            regressed=1,
            improved=0,
            unchanged=0,
            changed_but_valid=0,
            new_scenarios=0,
            missing_scenarios=0,
            impact_radius_percentage=100.0,
            scenarios=[
                ScenarioImpact(
                    scenario_id="t1",
                    classification="REGRESSED",
                    current_status="FAIL",
                    output_changed=True,
                )
            ],
        )

        with pytest.raises(PromptDriftError, match="Cannot accept 1 REGRESSED scenario"):
            selective_accept(current_baseline, new_report, impact)

    def test_accepts_regressions_when_allowed(self, current_baseline, new_report):
        from promptdrift.impact import ScenarioImpact

        impact = ImpactRadiusReport(
            total_scenarios=1,
            regressed=1,
            improved=0,
            unchanged=0,
            changed_but_valid=0,
            new_scenarios=0,
            missing_scenarios=0,
            impact_radius_percentage=100.0,
            scenarios=[
                ScenarioImpact(
                    scenario_id="t1",
                    classification="REGRESSED",
                    current_status="FAIL",
                    output_changed=True,
                )
            ],
        )

        new_b = selective_accept(current_baseline, new_report, impact, accept_regressions=True)
        assert new_b.tests["t1"].output_hash != current_baseline.tests["t1"].output_hash

    def test_rejects_changed_by_default(self, current_baseline, new_report):
        from promptdrift.impact import ScenarioImpact

        impact = ImpactRadiusReport(
            total_scenarios=1,
            regressed=0,
            improved=0,
            unchanged=0,
            changed_but_valid=1,
            new_scenarios=0,
            missing_scenarios=0,
            impact_radius_percentage=100.0,
            scenarios=[
                ScenarioImpact(
                    scenario_id="t1",
                    classification="CHANGED_BUT_VALID",
                    current_status="PASS",
                    output_changed=True,
                )
            ],
        )

        new_b = selective_accept(current_baseline, new_report, impact)
        # Should retain old t1
        assert new_b.tests["t1"].output_hash == "h1"

    def test_accepts_changed_when_allowed(self, current_baseline, new_report):
        from promptdrift.impact import ScenarioImpact

        impact = ImpactRadiusReport(
            total_scenarios=1,
            regressed=0,
            improved=0,
            unchanged=0,
            changed_but_valid=1,
            new_scenarios=0,
            missing_scenarios=0,
            impact_radius_percentage=100.0,
            scenarios=[
                ScenarioImpact(
                    scenario_id="t1",
                    classification="CHANGED_BUT_VALID",
                    current_status="PASS",
                    output_changed=True,
                )
            ],
        )

        new_b = selective_accept(current_baseline, new_report, impact, accept_changed=True)
        assert new_b.tests["t1"].output_hash != "h1"

    def test_selective_accept_by_id(self, current_baseline, new_report):
        from promptdrift.impact import ScenarioImpact

        impact = ImpactRadiusReport(
            total_scenarios=2,
            regressed=0,
            improved=0,
            unchanged=0,
            changed_but_valid=2,
            new_scenarios=0,
            missing_scenarios=0,
            impact_radius_percentage=100.0,
            scenarios=[
                ScenarioImpact(
                    scenario_id="t1",
                    classification="CHANGED_BUT_VALID",
                    current_status="PASS",
                    output_changed=True,
                ),
                ScenarioImpact(
                    scenario_id="t2",
                    classification="CHANGED_BUT_VALID",
                    current_status="PASS",
                    output_changed=True,
                ),
            ],
        )

        # We explicitly accept t1 but not t2
        new_b = selective_accept(current_baseline, new_report, impact, scenario_ids=["t1"])

        assert new_b.tests["t1"].output_hash != "h1"
        assert new_b.tests["t2"].output_hash == "h2"

    def test_preserves_metadata(self, current_baseline, new_report):
        from promptdrift.impact import ScenarioImpact

        impact = ImpactRadiusReport(
            total_scenarios=1,
            regressed=0,
            improved=0,
            unchanged=0,
            changed_but_valid=1,
            new_scenarios=0,
            missing_scenarios=0,
            impact_radius_percentage=100.0,
            current_git_sha="new_sha",
            current_prompt_hash="new_prompt",
            scenarios=[
                ScenarioImpact(
                    scenario_id="t1",
                    classification="CHANGED_BUT_VALID",
                    current_status="PASS",
                    output_changed=True,
                )
            ],
        )

        assert current_baseline.prompt_hash == "old_prompt"

        new_b = selective_accept(current_baseline, new_report, impact, accept_changed=True)
        assert new_b.git_sha == "new_sha"
        assert new_b.prompt_hash == "new_prompt"
