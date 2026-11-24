"""Execution engine for paired candidate-versus-control experiment runs."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from promptdrift.engine.provenance import fingerprint, with_response
from promptdrift.engine.runner import evaluate_response, evaluation_status
from promptdrift.errors import ProviderBudgetExceededError
from promptdrift.models import Config
from promptdrift.models.experiment import (
    ExperimentConfig,
    ExperimentReport,
    PairedArmResult,
    PairedScenarioComparison,
)
from promptdrift.models.result import EvaluationResult, ModelResponse
from promptdrift.models.test import TestCase
from promptdrift.providers import create_provider
from promptdrift.templates import render_prompt


def truncate_output(text: str, max_chars: int) -> str:
    """Keep memory and output bounded while preserving inspection."""
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}\n\n[Output truncated in experiment to keep within {max_chars} character limit]"


def _execute_arm(
    arm_name: str,
    provider: Any,
    test: TestCase,
    prompt: str,
    temperature: float | None,
    max_output_tokens: int | None,
    max_output_characters: int,
    config: Config,
) -> PairedArmResult:
    try:
        response: ModelResponse = provider.complete(
            prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        evaluations: list[EvaluationResult] = evaluate_response(test, response)
        status = evaluation_status(evaluations)
        bounded_output = truncate_output(response.output, max_output_characters)
        return PairedArmResult(
            arm=arm_name,
            test_id=test.id,
            provider=response.provider,
            model=response.model,
            output=bounded_output,
            latency_ms=response.latency_ms,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            estimated_cost_usd=response.estimated_cost_usd,
            provenance=with_response(fingerprint(config, test, prompt), response),
            evaluations=evaluations,
            status=status,
            error=None,
        )
    except Exception as exc:
        return PairedArmResult(
            arm=arm_name,
            test_id=test.id,
            provider=str(getattr(provider, "provider_name", "unknown")),
            model=str(getattr(provider, "model_name", "unknown")),
            output="",
            latency_ms=None,
            input_tokens=None,
            output_tokens=None,
            estimated_cost_usd=None,
            provenance=None,
            evaluations=[],
            status="ERROR",
            error=str(exc),
        )


def _compare_assertions(
    control_evals: list[EvaluationResult], candidate_evals: list[EvaluationResult]
) -> list[str]:
    diffs = []
    control_map = {e.assertion: e.passed for e in control_evals}
    candidate_map = {e.assertion: e.passed for e in candidate_evals}
    all_keys = sorted(set(control_map.keys()) | set(candidate_map.keys()))
    for key in all_keys:
        c_passed = control_map.get(key)
        cand_passed = candidate_map.get(key)
        if c_passed != cand_passed:
            diffs.append(
                f"{key}: control={'PASS' if c_passed else 'FAIL'} -> candidate={'PASS' if cand_passed else 'FAIL'}"
            )
    return diffs


def run_experiment(
    config: Config,
    experiment: ExperimentConfig,
    config_path: Path,
) -> ExperimentReport:
    """Execute a paired control-versus-candidate experiment on frozen rendered scenario inputs."""
    start_time = time.perf_counter()

    # Step 1: Freeze scenario inputs identically for both arms
    prepared: list[tuple[TestCase, str]] = [
        (test, render_prompt(config.resolve_path(config_path, test.prompt), test.variables))
        for test in config.tests
    ]

    total_planned_requests = len(prepared) * 2
    if experiment.request_budget is not None and total_planned_requests > experiment.request_budget:
        raise ProviderBudgetExceededError(
            f"Planned experiment requests ({total_planned_requests}) exceed experiment request budget ({experiment.request_budget})"
        )

    control_provider = create_provider(experiment.control.provider)
    candidate_provider = create_provider(experiment.candidate.provider)

    pairs: list[PairedScenarioComparison] = []
    total_requests = 0

    for test, prompt in prepared:
        # Control arm execution
        control_res = _execute_arm(
            arm_name=experiment.control.name,
            provider=control_provider,
            test=test,
            prompt=prompt,
            temperature=experiment.control.temperature or config.defaults.temperature,
            max_output_tokens=experiment.control.max_output_tokens
            or config.defaults.max_output_tokens,
            max_output_characters=experiment.max_output_characters,
            config=config,
        )
        total_requests += 1

        # Candidate arm execution
        candidate_res = _execute_arm(
            arm_name=experiment.candidate.name,
            provider=candidate_provider,
            test=test,
            prompt=prompt,
            temperature=experiment.candidate.temperature or config.defaults.temperature,
            max_output_tokens=experiment.candidate.max_output_tokens
            or config.defaults.max_output_tokens,
            max_output_characters=experiment.max_output_characters,
            config=config,
        )
        total_requests += 1

        # Latency delta (candidate - control)
        latency_delta = (
            round(candidate_res.latency_ms - control_res.latency_ms, 2)
            if (candidate_res.latency_ms is not None and control_res.latency_ms is not None)
            else None
        )

        # Cost delta (candidate - control)
        cost_delta = (
            round(candidate_res.estimated_cost_usd - control_res.estimated_cost_usd, 6)
            if (
                candidate_res.estimated_cost_usd is not None
                and control_res.estimated_cost_usd is not None
            )
            else None
        )

        # Token delta (total tokens candidate - total tokens control)
        cand_tokens = (
            (candidate_res.input_tokens or 0) + (candidate_res.output_tokens or 0)
            if (candidate_res.input_tokens is not None or candidate_res.output_tokens is not None)
            else None
        )
        ctrl_tokens = (
            (control_res.input_tokens or 0) + (control_res.output_tokens or 0)
            if (control_res.input_tokens is not None or control_res.output_tokens is not None)
            else None
        )
        token_delta = (
            cand_tokens - ctrl_tokens
            if (cand_tokens is not None and ctrl_tokens is not None)
            else None
        )

        assertion_changes = _compare_assertions(control_res.evaluations, candidate_res.evaluations)

        # Pairing status determination
        # Critical rule: A failed arm is NEVER treated as a passing comparison
        if control_res.status == "ERROR" or candidate_res.status == "ERROR":
            status = "INCOMPARABLE"
        elif control_res.status == "FAIL" or candidate_res.status == "FAIL":
            status = "FAIL"
        elif control_res.status == "WARN" or candidate_res.status == "WARN":
            status = "WARN"
        else:
            status = "PASS"

        pairs.append(
            PairedScenarioComparison(
                scenario_id=test.id,
                input=prompt,
                control=control_res,
                candidate=candidate_res,
                status=status,
                latency_delta_ms=latency_delta,
                cost_delta_usd=cost_delta,
                token_delta=token_delta,
                assertion_changes=assertion_changes,
            )
        )

    passed_count = sum(1 for p in pairs if p.status == "PASS")
    failed_count = sum(1 for p in pairs if p.status == "FAIL")
    incomparable_count = sum(1 for p in pairs if p.status == "INCOMPARABLE")

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

    return ExperimentReport(
        name=experiment.name,
        control_arm=experiment.control.name,
        candidate_arm=experiment.candidate.name,
        pairs=pairs,
        total_pairs=len(pairs),
        passed_pairs=passed_count,
        failed_pairs=failed_count,
        incomparable_pairs=incomparable_count,
        total_requests=total_requests,
        duration_ms=duration_ms,
    )
