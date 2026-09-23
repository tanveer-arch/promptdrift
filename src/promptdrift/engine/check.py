"""Orchestration for git-aware selective scenario check and impact analysis."""

from __future__ import annotations

from pathlib import Path

from promptdrift.engine.baseline import load_baseline
from promptdrift.engine.runner import run_suite
from promptdrift.git import GitContext
from promptdrift.impact import ImpactRadiusReport, calculate_impact_radius
from promptdrift.models import Config, RegressionReport, TestCase
from promptdrift.models.capture import Scenario
from promptdrift.storage.scenarios import load_scenarios


def scenario_to_test_case(
    scenario: Scenario, default_prompt: str = "prompts/example.txt"
) -> TestCase:
    prompt_path = scenario.prompt or default_prompt
    variables = dict(scenario.variables)
    if "input" not in variables and scenario.input:
        variables["input"] = scenario.input
    return TestCase(
        id=scenario.id,
        prompt=prompt_path,
        variables=variables,
        assertions=scenario.assertions,
        thresholds=scenario.thresholds,
    )


def orchestrate_check(
    config: Config,
    config_path: Path,
    *,
    base_ref: str | None = None,
    scenario_file: Path | None = None,
) -> tuple[RegressionReport, ImpactRadiusReport]:
    git = GitContext(root=config_path.parent)
    changed_files = git.get_changed_files(base_ref=base_ref)

    # Collect tests from config and from scenario store
    tests: list[TestCase] = list(config.tests)
    scenario_metadata: dict[str, dict] = {}

    scenarios_path = scenario_file or (
        config.resolve_path(config_path, config.scenarios.file)
        if config.scenarios
        else config_path.parent / ".promptdrift" / "scenarios.json"
    )

    if scenarios_path.is_file():
        scenario_lib = load_scenarios(scenarios_path)
        existing_test_ids = {t.id for t in tests}
        for sc in scenario_lib.scenarios:
            if sc.status == "promoted" and sc.id not in existing_test_ids:
                tc = scenario_to_test_case(sc)
                tests.append(tc)
                scenario_metadata[sc.id] = {
                    "category": sc.category or "general",
                    "prompt": sc.prompt,
                }

    # Selective scenario execution if git changed files are available
    selected_tests = tests
    skipped_ids: set[str] = set()
    if changed_files:
        affected: list[TestCase] = []
        for t in tests:
            rel_prompt = str(Path(t.prompt)).replace("\\", "/")
            if any(rel_prompt in cf.replace("\\", "/") for cf in changed_files):
                affected.append(t)
        if affected:
            skipped_ids = {t.id for t in tests} - {t.id for t in affected}
            selected_tests = affected

    active_config = config.model_copy(deep=True)
    active_config.tests = selected_tests

    # If no tests exist to run, raise or return empty
    report = run_suite(active_config, config_path)

    baseline_path = config.resolve_path(config_path, config.baseline.path)
    baseline = None
    if baseline_path.exists():
        try:
            baseline = load_baseline(baseline_path)
            report.baseline_path = str(baseline_path)
        except Exception:
            pass

    current_git_sha = git.get_head_sha()
    prompt_paths = [config.resolve_path(config_path, t.prompt) for t in tests]
    current_prompt_hash = git.compute_prompt_hash(prompt_paths)

    impact = calculate_impact_radius(
        report,
        baseline,
        scenario_metadata=scenario_metadata,
        skipped_ids=skipped_ids,
        current_git_sha=current_git_sha,
        current_prompt_hash=current_prompt_hash,
    )
    return report, impact
