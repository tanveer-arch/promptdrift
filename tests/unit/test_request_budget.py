"""Every provider attempt, retries included, counts against one run's request budget."""

import json

import httpx
import pytest
from typer.testing import CliRunner

from promptdrift.cli import app
from promptdrift.engine.monitor import monitor_suite
from promptdrift.engine.runner import run_suite
from promptdrift.errors import ProviderBudgetExceededError, ProviderTransportError
from promptdrift.models import Config
from promptdrift.models.config import ProviderConfig, ResilienceConfig
from promptdrift.models.result import ModelResponse
from promptdrift.providers import MockProvider, RequestBudget, ResilienceExecutor, create_provider

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
EXHAUSTED = r"Request budget of 3 exhausted after 3 provider attempts \(2 were retries\)"


class FakeClock:
    def __init__(self):
        self.current = 0.0
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.current

    def sleep(self, duration: float) -> None:
        self.sleeps.append(duration)
        self.current += duration


def unavailable(timeout: float) -> ModelResponse:
    raise ProviderTransportError("OpenAI request failed: HTTPStatusError (503)")


def scripted_transport(monkeypatch, statuses: list[int]) -> list[int]:
    """Replace the OpenAI HTTP transport; returns the log of statuses actually served."""
    served: list[int] = []

    def fake_post(*args, **kwargs):
        if len(served) == len(statuses):
            pytest.fail("provider made an HTTP request after its script ended")
        status = statuses[len(served)]
        served.append(status)
        body = {"choices": [{"message": {"content": "ok"}}]} if status == 200 else {}
        return httpx.Response(status, json=body, request=httpx.Request("POST", OPENAI_URL))

    monkeypatch.setenv("TEST_KEY", "sk-test")
    monkeypatch.setattr("promptdrift.providers.openai.httpx.post", fake_post)
    return served


def openai_config(tmp_path, *, tests: int, request_budget: int | None, max_retries: int = 2):
    (tmp_path / "prompt.txt").write_text("Hello {{ name }}", encoding="utf-8")
    return Config.model_validate(
        {
            "provider": {
                "type": "openai",
                "model": "gpt-test",
                "api_key_env": "TEST_KEY",
                # Tiny real backoff: engine-built providers use the default sleeper.
                "resilience": {
                    "max_retries": max_retries,
                    "initial_backoff": 0.001,
                    "request_budget": request_budget,
                },
            },
            "tests": [
                {"id": f"t{index}", "prompt": "prompt.txt", "variables": {"name": str(index)}}
                for index in range(tests)
            ],
        }
    )


class TestRequestBudget:
    def test_consume_counts_attempts_and_retries(self):
        budget = RequestBudget(3)
        budget.consume()
        budget.consume(retry=True)
        budget.consume(retry=True)
        assert (budget.attempts, budget.retries) == (3, 2)
        with pytest.raises(ProviderBudgetExceededError, match=EXHAUSTED):
            budget.consume(retry=True)
        assert budget.attempts == 3

    def test_message_says_how_to_fix_it(self):
        budget = RequestBudget(1)
        budget.consume()
        with pytest.raises(ProviderBudgetExceededError) as info:
            budget.check()
        assert "provider.resilience.request_budget" in str(info.value)
        assert "max_retries/samples" in str(info.value)


class TestExecutorRetries:
    def test_transient_failures_stop_when_budget_is_used_up(self):
        clock = FakeClock()
        calls = []
        executor = ResilienceExecutor(
            ResilienceConfig(max_retries=5, initial_backoff=1.0),
            "OpenAI",
            clock=clock.now,
            sleeper=clock.sleep,
            budget=RequestBudget(3),
        )

        def call(timeout):
            calls.append(timeout)
            return unavailable(timeout)

        with pytest.raises(ProviderBudgetExceededError, match=EXHAUSTED):
            executor.execute(call)
        assert len(calls) == 3
        # Backoff happened only before retries that were actually made.
        assert clock.sleeps == [1.0, 2.0]

    def test_without_budget_all_retries_still_run(self):
        clock = FakeClock()
        calls = []
        executor = ResilienceExecutor(
            ResilienceConfig(max_retries=4, initial_backoff=1.0),
            "OpenAI",
            clock=clock.now,
            sleeper=clock.sleep,
        )

        def call(timeout):
            calls.append(timeout)
            return unavailable(timeout)

        with pytest.raises(ProviderTransportError):
            executor.execute(call)
        assert len(calls) == 5
        assert executor.budget is None

    def test_successful_attempts_share_the_same_budget(self):
        budget = RequestBudget(2)
        executor = ResilienceExecutor(ResilienceConfig(), "OpenAI", budget=budget)
        response = ModelResponse(output="ok", latency_ms=1, model="m", provider="openai")
        executor.execute(lambda timeout: response)
        executor.execute(lambda timeout: response)
        with pytest.raises(ProviderBudgetExceededError):
            executor.execute(lambda timeout: pytest.fail("attempt made after exhaustion"))
        assert (budget.attempts, budget.retries) == (2, 0)


class TestProviders:
    def test_mock_counts_every_call(self):
        provider = MockProvider(ProviderConfig(type="mock", model="echo"), budget=RequestBudget(2))
        for _ in range(2):
            provider.complete("hi", temperature=0, max_output_tokens=10)
        with pytest.raises(ProviderBudgetExceededError):
            provider.complete("hi", temperature=0, max_output_tokens=10)

    @pytest.mark.parametrize("provider_type", ["mock", "openai", "ollama", "anthropic"])
    def test_create_provider_defaults_to_unlimited(self, provider_type):
        provider = create_provider(ProviderConfig(type=provider_type, model="m"))
        holder = provider if provider_type == "mock" else provider.executor
        assert holder.budget is None

    def test_openai_stops_http_requests_at_the_budget(self, monkeypatch):
        served = scripted_transport(monkeypatch, [503, 503, 503])
        clock = FakeClock()
        provider = create_provider(
            ProviderConfig(type="openai", model="m", api_key_env="TEST_KEY", max_retries=5),
            budget=RequestBudget(3),
        )
        provider.executor.clock, provider.executor.sleeper = clock.now, clock.sleep
        with pytest.raises(ProviderBudgetExceededError, match=EXHAUSTED):
            provider.complete("hi", temperature=0, max_output_tokens=10)
        assert served == [503, 503, 503]


class TestRunsShareOneBudget:
    def test_test_cases_share_the_budget_with_retries(self, tmp_path, monkeypatch):
        # t0 needs three attempts (two retries); nothing is left for t1.
        served = scripted_transport(monkeypatch, [503, 503, 200])
        config = openai_config(tmp_path, tests=2, request_budget=3)
        with pytest.raises(ProviderBudgetExceededError, match=EXHAUSTED):
            run_suite(config, tmp_path / "promptdrift.yaml")
        assert served == [503, 503, 200]

    def test_monitor_samples_and_retries_share_the_budget(self, tmp_path, monkeypatch):
        # Sample 1 succeeds on a retry; sample 2's first attempt fails and its retry
        # would be the fourth attempt, so the run stops instead of reporting provider_error.
        served = scripted_transport(monkeypatch, [503, 200, 503])
        config = openai_config(tmp_path, tests=1, request_budget=3)
        (tmp_path / "promptdrift.baseline.json").write_text(
            json.dumps(
                {
                    "schema_version": 3,
                    "promptdrift_version": "0.1.0",
                    "generated_at": "2026-01-01T00:00:00Z",
                    "provider": {"type": "openai", "model": "gpt-test"},
                    "tests": {},
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(
            ProviderBudgetExceededError,
            match=r"exhausted after 3 provider attempts \(1 was a retry\)",
        ):
            monitor_suite(config, tmp_path / "promptdrift.yaml", samples=2)
        assert served == [503, 200, 503]

    def test_cli_monitor_reports_the_actionable_message(self, tmp_path, monkeypatch):
        served = scripted_transport(monkeypatch, [503, 503, 503])
        config = openai_config(tmp_path, tests=1, request_budget=3, max_retries=3)
        path = tmp_path / "promptdrift.yaml"
        path.write_text(json.dumps(config.model_dump(mode="json")), encoding="utf-8")
        (tmp_path / "promptdrift.baseline.json").write_text(
            json.dumps(
                {
                    "schema_version": 3,
                    "promptdrift_version": "0.1.0",
                    "generated_at": "2026-01-01T00:00:00Z",
                    "provider": {"type": "openai", "model": "gpt-test"},
                    "tests": {},
                }
            ),
            encoding="utf-8",
        )
        result = CliRunner().invoke(
            app,
            ["monitor", "--config", str(path), "--samples", "1", "--json", "--no-history"],
        )
        assert result.exit_code == 3
        error = json.loads(result.stdout)["error"]
        assert error["type"] == "ProviderBudgetExceededError"
        assert error["message"].startswith("Request budget of 3 exhausted")
        assert served == [503, 503, 503]

    def test_no_budget_keeps_previous_behaviour(self, tmp_path, monkeypatch):
        served = scripted_transport(monkeypatch, [503, 503, 200, 200])
        config = openai_config(tmp_path, tests=2, request_budget=None)
        report = run_suite(config, tmp_path / "promptdrift.yaml")
        assert [run.output for run in report.tests] == ["ok", "ok"]
        assert served == [503, 503, 200, 200]
