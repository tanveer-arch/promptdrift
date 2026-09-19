"""Optional semantic evaluators protocol and lightweight embeddings/judge abstractions."""

from __future__ import annotations

from typing import Protocol

from promptdrift.models.result import EvaluationResult, ModelResponse
from promptdrift.models.test import TestCase


class Evaluator(Protocol):
    def evaluate(self, case: TestCase, response: ModelResponse) -> EvaluationResult: ...


class ExactSimilarityEvaluator:
    def __init__(self, threshold: float = 0.8) -> None:
        self.threshold = threshold

    def evaluate(self, case: TestCase, response: ModelResponse) -> EvaluationResult:
        # Simple deterministic character-based similarity metric for fallback/local test
        expected = str(case.variables.get("expected", ""))
        actual = response.output
        if not expected:
            return EvaluationResult(
                passed=True,
                assertion="semantic_similarity",
                expected=self.threshold,
                actual=1.0,
                reason="No reference text to compare against.",
                severity="warn",
            )
        common = sum(1 for a, b in zip(expected, actual, strict=False) if a == b)
        score = common / max(len(expected), len(actual), 1)
        passed = score >= self.threshold
        return EvaluationResult(
            passed=passed,
            assertion="semantic_similarity",
            expected=self.threshold,
            actual=round(score, 2),
            reason="Semantic similarity threshold met."
            if passed
            else "Semantic similarity below threshold.",
            severity="warn" if passed else "fail",
        )
