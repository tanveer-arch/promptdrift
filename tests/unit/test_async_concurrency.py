"""Unit tests for bounded asynchronous provider execution and batch concurrency (#71)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import httpx
import pytest

from promptdrift.engine.baseline import write_baseline
from promptdrift.engine.monitor import monitor_suite
from promptdrift.engine.runner import AtomicRequestBudget, run_suite
from promptdrift.errors import ProviderAuthError, ProviderBudgetExceededError, ProviderTimeoutError
from promptdrift.models import Config, ProviderConfig, ResilienceConfig
from promptdrift.models import TestCase as DriftTestCase
from promptdrift.models.config import Defaults
from promptdrift.models.result import ModelResponse
from promptdrift.providers.mock import MockProvider
from promptdrift.providers.openai import OpenAIProvider
from promptdrift.providers.resilience import ResilienceExecutor


def test_concurrency_config_validation():
    # Default is 1
    default_cfg = ResilienceConfig()
    assert default_cfg.concurrency == 1

    # Valid values
    custom_cfg = ResilienceConfig(concurrency=5)
    assert custom_cfg.concurrency == 5

    max_cfg = ResilienceConfig(concurrency=20)
    assert max_cfg.concurrency == 20

    # Invalid values
    with pytest.raises(ValueError):
        ResilienceConfig(concurrency=0)

    with pytest.raises(ValueError):
        ResilienceConfig(concurrency=25)


def test_mock_provider_acomplete():
    async def _run():
        provider = MockProvider(ProviderConfig(type="mock", model="mock-model"))
        response = await provider.acomplete("Hello world", temperature=0.7, max_output_tokens=100)
        assert isinstance(response, ModelResponse)
        assert response.output == "Hello world"
        assert response.provider == "mock"

    asyncio.run(_run())


def test_openai_provider_acomplete_auth_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = OpenAIProvider(ProviderConfig(type="openai", model="gpt-4o-mini"))

    async def _run():
        with pytest.raises(ProviderAuthError):
            await provider.acomplete("Hello", temperature=0.0, max_output_tokens=50)

    asyncio.run(_run())


def test_openai_provider_acomplete_mocked_transport(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-mock")

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Async hello world"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3},
                "model": "gpt-4o-mini",
            },
        )

    transport = httpx.MockTransport(mock_handler)
    provider = OpenAIProvider(ProviderConfig(type="openai", model="gpt-4o-mini"))

    async def _run():
        with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
            response = await provider.acomplete(
                "Test prompt", temperature=0.0, max_output_tokens=50
            )
            assert response.output == "Async hello world"
            assert response.provider == "openai"
            assert response.input_tokens == 5
            assert response.output_tokens == 3

    asyncio.run(_run())


def test_resilience_executor_aexecute_retry():
    config = ResilienceConfig(max_retries=2, initial_backoff=0.01)
    executor = ResilienceExecutor(config, provider_name="TestProvider")

    attempts = 0

    async def transient_fn(timeout: float):
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise httpx.TransportError("Network glitch")
        return ModelResponse(
            output="Success",
            model="test",
            provider="test",
            latency_ms=10.0,
            input_tokens=1,
            output_tokens=1,
        )

    async def _run():
        res = await executor.aexecute(transient_fn)
        assert res.output == "Success"
        assert attempts == 2

    asyncio.run(_run())


def test_resilience_executor_aexecute_timeout_budget():
    config = ResilienceConfig(timeout_budget=0.05, max_retries=3, initial_backoff=0.1)
    executor = ResilienceExecutor(config, provider_name="TestProvider")

    async def slow_failing(timeout: float):
        await asyncio.sleep(0.06)
        raise httpx.TransportError("Network glitch")

    async def _run():
        with pytest.raises(ProviderTimeoutError):
            await executor.aexecute(slow_failing)

    asyncio.run(_run())


def test_atomic_request_budget():
    async def _run():
        budget = AtomicRequestBudget(limit=3)

        # 3 acquires succeed
        await budget.acquire()
        await budget.acquire()
        await budget.acquire()

        # 4th acquire raises
        with pytest.raises(ProviderBudgetExceededError):
            await budget.acquire()

    asyncio.run(_run())


def test_run_suite_concurrent_execution(tmp_path):
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("Echo {{ value }}", encoding="utf-8")

    tests = [
        DriftTestCase(id=f"test-{i}", prompt=str(prompt_file), variables={"value": f"val-{i}"})
        for i in range(10)
    ]

    config = Config(
        provider=ProviderConfig(
            type="mock",
            model="mock-model",
            resilience=ResilienceConfig(concurrency=5),
        ),
        tests=tests,
        defaults=Defaults(),
    )

    report = run_suite(config, tmp_path / "promptdrift.yaml")

    # Deterministic result count and ordering
    assert len(report.tests) == 10
    for idx, test_run in enumerate(report.tests):
        assert test_run.test_id == f"test-{idx}"
        assert test_run.output == f"Echo val-{idx}"


def test_run_suite_concurrent_request_budget_exceeded(tmp_path):
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("Echo {{ value }}", encoding="utf-8")

    tests = [
        DriftTestCase(id=f"test-{i}", prompt=str(prompt_file), variables={"value": f"val-{i}"})
        for i in range(5)
    ]

    config = Config(
        provider=ProviderConfig(
            type="mock",
            model="mock-model",
            resilience=ResilienceConfig(concurrency=3, request_budget=3),
        ),
        tests=tests,
        defaults=Defaults(),
    )

    with pytest.raises(ProviderBudgetExceededError):
        run_suite(config, tmp_path / "promptdrift.yaml")


def test_monitor_suite_concurrent_execution(tmp_path):
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("Monitor prompt {{ id }}", encoding="utf-8")

    tests = [
        DriftTestCase(
            id=f"test-{i}",
            prompt="prompt.txt",
            variables={"id": str(i)},
            assertions=[{"type": "contains", "value": f"Monitor prompt {i}"}],
        )
        for i in range(4)
    ]

    config_path = tmp_path / "promptdrift.yaml"
    config = Config(
        provider=ProviderConfig(
            type="mock",
            model="mock-model",
            resilience=ResilienceConfig(concurrency=4),
        ),
        tests=tests,
        defaults=Defaults(),
    )

    config_path.write_text(json.dumps(config.model_dump(mode="json")), encoding="utf-8")
    write_baseline(tmp_path / config.baseline.path, run_suite(config, config_path))

    report = monitor_suite(config, config_path, samples=3)

    assert len(report.tests) == 4
    for idx, case in enumerate(report.tests):
        assert case.test_id == f"test-{idx}"
        assert case.samples == 3
        assert len(case.samples_detail) == 3
        for s in case.samples_detail:
            assert s.status == "PASS"
            assert s.output_hash is not None
