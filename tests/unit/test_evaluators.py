from promptdrift.evaluators import evaluate_assertion
from promptdrift.models.result import ModelResponse
from promptdrift.models.test import Assertion


def response(text="hello world"):
    return ModelResponse(output=text, latency_ms=12, model="test", provider="mock", output_tokens=2, estimated_cost_usd=0)


def test_contains_and_not_contains():
    assert evaluate_assertion(Assertion(type="contains", value="hello"), response()).passed
    assert not evaluate_assertion(Assertion(type="not_contains", value="hello"), response()).passed


def test_json_schema_reason():
    result = evaluate_assertion(Assertion(type="json_schema", schema={"type": "object", "required": ["ok"]}), response("{}"))
    assert not result.passed
    assert "required" in result.reason


def test_latency_limit():
    assert not evaluate_assertion(Assertion(type="latency_ms", value=10), response()).passed
