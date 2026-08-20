"""Execution engine connecting templates, providers, contracts and baselines."""
from __future__ import annotations

import time
from pathlib import Path

from promptdrift.evaluators import evaluate_assertion
from promptdrift.models import Config, RegressionReport, TestRun
from promptdrift.providers import create_provider
from promptdrift.templates import render_prompt


def _threshold_results(test, response):
    """Translate shorthand thresholds into deterministic warning/failure evaluations."""
    results = []
    for metric, threshold in test.thresholds.items():
        warning = threshold.warn if hasattr(threshold, "warn") else None
        failure = threshold.fail if hasattr(threshold, "fail") else float(threshold)
        actual = response.latency_ms if metric == "latency_ms" else (response.estimated_cost_usd or 0.0)
        if failure is not None and actual > failure:
            from promptdrift.models.result import EvaluationResult
            results.append(EvaluationResult(passed=False, assertion=metric, expected=failure, actual=actual,
                reason=f"{metric} exceeded failure threshold.", severity="fail"))
        elif warning is not None and actual > warning:
            from promptdrift.models.result import EvaluationResult
            results.append(EvaluationResult(passed=False, assertion=metric, expected=warning, actual=actual,
                reason=f"{metric} exceeded warning threshold.", severity="warn"))
    return results


def run_suite(config: Config, config_path: Path) -> RegressionReport:
    start = time.perf_counter()
    provider = create_provider(config.provider)
    runs: list[TestRun] = []
    for test in config.tests:
        prompt = render_prompt(config.resolve_path(config_path, test.prompt), test.variables)
        response = provider.complete(prompt, temperature=config.defaults.temperature,
                                     max_output_tokens=config.defaults.max_output_tokens)
        evaluations = [evaluate_assertion(assertion, response) for assertion in test.assertions]
        evaluations.extend(_threshold_results(test, response))
        status = "FAIL" if any(not item.passed and item.severity == "fail" for item in evaluations) else (
            "WARN" if any(not item.passed for item in evaluations) else "PASS")
        runs.append(TestRun(test_id=test.id, provider=response.provider, model=response.model, input=prompt,
            output=response.output, latency_ms=response.latency_ms, input_tokens=response.input_tokens,
            output_tokens=response.output_tokens, estimated_cost_usd=response.estimated_cost_usd,
            evaluations=evaluations, status=status))
    return RegressionReport(provider=config.provider.type, model=config.provider.model, tests=runs,
                            duration_ms=round((time.perf_counter()-start)*1000, 2))
