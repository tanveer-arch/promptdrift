"""Comprehensive tests for all deterministic assertion evaluators."""

import pytest
from pydantic import ValidationError

from promptdrift.evaluators import evaluate_assertion
from promptdrift.models.result import ModelResponse
from promptdrift.models.test import Assertion


def response(text="hello world", latency_ms=12, output_tokens=2, cost=0.001):
    return ModelResponse(
        output=text,
        latency_ms=latency_ms,
        model="test",
        provider="mock",
        output_tokens=output_tokens,
        estimated_cost_usd=cost,
    )


# --- exact_match ---


class TestExactMatch:
    def test_passes_on_identical_text(self):
        result = evaluate_assertion(Assertion(type="exact_match", value="hello world"), response())
        assert result.passed

    def test_fails_on_different_text(self):
        result = evaluate_assertion(Assertion(type="exact_match", value="goodbye"), response())
        assert not result.passed

    def test_is_case_sensitive(self):
        result = evaluate_assertion(Assertion(type="exact_match", value="Hello World"), response())
        assert not result.passed

    def test_fails_on_extra_whitespace(self):
        result = evaluate_assertion(Assertion(type="exact_match", value="hello world "), response())
        assert not result.passed

    def test_empty_string_matches_empty(self):
        result = evaluate_assertion(Assertion(type="exact_match", value=""), response(""))
        assert result.passed


# --- contains ---


class TestContains:
    def test_passes_when_substring_present(self):
        assert evaluate_assertion(Assertion(type="contains", value="hello"), response()).passed

    def test_fails_when_substring_absent(self):
        assert not evaluate_assertion(
            Assertion(type="contains", value="goodbye"), response()
        ).passed

    def test_is_case_sensitive(self):
        assert not evaluate_assertion(Assertion(type="contains", value="HELLO"), response()).passed

    def test_empty_value_always_matches(self):
        assert evaluate_assertion(Assertion(type="contains", value=""), response()).passed

    def test_works_with_numeric_value(self):
        assert evaluate_assertion(
            Assertion(type="contains", value=42), response("The answer is 42")
        ).passed

    def test_works_with_unicode(self):
        assert evaluate_assertion(
            Assertion(type="contains", value="日本"), response("Welcome to 日本語")
        ).passed


# --- not_contains ---


class TestNotContains:
    def test_passes_when_forbidden_text_absent(self):
        assert evaluate_assertion(
            Assertion(type="not_contains", value="goodbye"), response()
        ).passed

    def test_fails_when_forbidden_text_present(self):
        assert not evaluate_assertion(
            Assertion(type="not_contains", value="hello"), response()
        ).passed

    def test_empty_forbidden_string_always_fails(self):
        assert not evaluate_assertion(Assertion(type="not_contains", value=""), response()).passed


# --- starts_with ---


class TestStartsWith:
    def test_passes_when_prefix_matches(self):
        assert evaluate_assertion(
            Assertion(type="starts_with", value="hello"), response("hello world")
        ).passed

    def test_fails_when_prefix_does_not_match(self):
        assert not evaluate_assertion(
            Assertion(type="starts_with", value="goodbye"), response("hello world")
        ).passed

    def test_empty_prefix_always_matches(self):
        assert evaluate_assertion(Assertion(type="starts_with", value=""), response("anything")).passed

    def test_works_with_special_characters(self):
        assert evaluate_assertion(
            Assertion(type="starts_with", value="<json>"), response("<json>{}")
        ).passed

    def test_case_sensitive(self):
        assert not evaluate_assertion(
            Assertion(type="starts_with", value="Hello"), response("hello world")
        ).passed

    def test_numeric_value_cast_to_string(self):
        assert evaluate_assertion(
            Assertion(type="starts_with", value=42), response("42 is the answer")
        ).passed


# --- ends_with ---


class TestEndsWith:
    def test_passes_when_suffix_matches(self):
        assert evaluate_assertion(
            Assertion(type="ends_with", value="world"), response("hello world")
        ).passed

    def test_fails_when_suffix_does_not_match(self):
        assert not evaluate_assertion(
            Assertion(type="ends_with", value="goodbye"), response("hello world")
        ).passed

    def test_empty_suffix_always_matches(self):
        assert evaluate_assertion(Assertion(type="ends_with", value=""), response("anything")).passed

    def test_works_with_special_characters(self):
        assert evaluate_assertion(
            Assertion(type="ends_with", value="```"), response("code\n```")
        ).passed

    def test_case_sensitive(self):
        assert not evaluate_assertion(
            Assertion(type="ends_with", value="World"), response("hello world")
        ).passed

    def test_numeric_value_cast_to_string(self):
        assert evaluate_assertion(
            Assertion(type="ends_with", value=42), response("the answer is 42")
        ).passed


# --- unsupported ---


class TestUnsupported:
    def test_unsupported_type_raises_error(self):
        # Create assertion-like object that bypasses validation
        with pytest.raises(Exception):
            evaluate_assertion(Assertion(type="nonexistent", value="x"), response())


# --- severity ---


class TestSeverity:
    def test_default_severity_is_fail(self):
        result = evaluate_assertion(Assertion(type="contains", value="missing"), response())
        assert result.severity == "fail"

    def test_warn_severity_is_preserved(self):
        result = evaluate_assertion(
            Assertion(type="contains", value="missing", severity="warn"), response()
        )
        assert result.severity == "warn"

    def test_custom_name_used_as_label(self):
        result = evaluate_assertion(
            Assertion(type="contains", value="hello", name="greeting_check"), response()
        )
        assert result.assertion == "greeting_check"
