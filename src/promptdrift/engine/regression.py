"""Baseline comparison: changed output is a diagnostic, not automatically a failure."""
from __future__ import annotations

import hashlib

from promptdrift.models import Baseline, RegressionReport


def compare_to_baseline(report: RegressionReport, baseline: Baseline) -> RegressionReport:
    for run in report.tests:
        old = baseline.tests.get(run.test_id)
        if old is None:
            if run.status == "PASS":
                run.status = "WARN"
                run.evaluations.append(_diagnostic("baseline", "existing test", "new test", "Test has no baseline."))
            continue
        changed = hashlib.sha256(run.output.encode()).hexdigest() != old.output_hash
        if changed and run.status == "PASS":
            # An output change retains PASS because no behavioral contract has been violated.
            run.evaluations.append(_diagnostic("output_change", "baseline output", "changed output",
                "Output changed, but all behavioral assertions still pass."))
    return report


def _diagnostic(name, expected, actual, reason):
    from promptdrift.models.result import EvaluationResult
    return EvaluationResult(passed=True, assertion=name, expected=expected, actual=actual, reason=reason, severity="warn")
