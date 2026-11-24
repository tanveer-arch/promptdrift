"""Tests for paired candidate-versus-control experiment runs with comparable provenance."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from promptdrift.cli import app
from promptdrift.engine.experiment import run_experiment, truncate_output
from promptdrift.errors import ProviderBudgetExceededError
from promptdrift.models import (
    Assertion,
    Config,
    ExperimentArmConfig,
    ExperimentConfig,
    ModelResponse,
    ProviderConfig,
)
from promptdrift.models import (
    TestCase as DriftTestCase,
)


@pytest.fixture
def base_config(tmp_path: Path) -> tuple[Config, Path]:
    prompt_file = tmp_path / "prompt.jinja"
    prompt_file.write_text("Hello {{ name }}, solve {{ task }}.", encoding="utf-8")

    test_case = DriftTestCase(
        id="test-greeting",
        prompt="prompt.jinja",
        variables={"name": "Alice", "task": "math"},
        assertions=[
            Assertion(type="contains", value="Alice"),
        ],
    )

    config = Config(
        provider=ProviderConfig(type="mock", model="mock-control"),
        tests=[test_case],
    )
    config_path = tmp_path / "promptdrift.yaml"
    return config, config_path


class TestPairedExperiment:
    def test_truncate_output(self):
        short_text = "Short text"
        assert truncate_output(short_text, 100) == "Short text"

        long_text = "A" * 150
        truncated = truncate_output(long_text, 50)
        assert len(truncated) > 50
        assert truncated.startswith("A" * 50)
        assert "[Output truncated in experiment" in truncated

    def test_identical_frozen_inputs_both_arms(self, base_config):
        config, config_path = base_config

        control_arm = ExperimentArmConfig(
            name="control",
            provider=ProviderConfig(type="mock", model="ctrl-model"),
        )
        candidate_arm = ExperimentArmConfig(
            name="candidate",
            provider=ProviderConfig(type="mock", model="cand-model"),
        )
        exp_config = ExperimentConfig(
            name="test_exp",
            control=control_arm,
            candidate=candidate_arm,
        )

        mock_ctrl_provider = MagicMock()
        mock_ctrl_provider.complete.return_value = ModelResponse(
            output="Hello Alice, here is your answer.",
            latency_ms=100.0,
            input_tokens=10,
            output_tokens=20,
            model="ctrl-model",
            provider="mock",
            estimated_cost_usd=0.001,
        )

        mock_cand_provider = MagicMock()
        mock_cand_provider.complete.return_value = ModelResponse(
            output="Greetings Alice, here is your response.",
            latency_ms=150.0,
            input_tokens=10,
            output_tokens=25,
            model="cand-model",
            provider="mock",
            estimated_cost_usd=0.0015,
        )

        with patch("promptdrift.engine.experiment.create_provider") as mock_create:
            mock_create.side_effect = [mock_ctrl_provider, mock_cand_provider]
            report = run_experiment(config, exp_config, config_path)

        assert report.total_pairs == 1
        assert report.passed_pairs == 1
        assert report.failed_pairs == 0
        pair = report.pairs[0]
        assert pair.scenario_id == "test-greeting"
        assert pair.input == "Hello Alice, solve math."
        assert pair.control.output == "Hello Alice, here is your answer."
        assert pair.candidate.output == "Greetings Alice, here is your response."
        assert pair.status == "PASS"
        assert pair.latency_delta_ms == 50.0
        assert pair.token_delta == 5  # (10+25) - (10+20) = 5
        assert pair.cost_delta_usd == 0.0005

        # Confirm both providers received the exact same frozen rendered prompt
        mock_ctrl_provider.complete.assert_called_once_with(
            "Hello Alice, solve math.",
            temperature=config.defaults.temperature,
            max_output_tokens=config.defaults.max_output_tokens,
        )
        mock_cand_provider.complete.assert_called_once_with(
            "Hello Alice, solve math.",
            temperature=config.defaults.temperature,
            max_output_tokens=config.defaults.max_output_tokens,
        )

    def test_failed_arm_never_treated_as_passing(self, base_config):
        config, config_path = base_config

        control_arm = ExperimentArmConfig(name="control", provider=ProviderConfig(type="mock"))
        candidate_arm = ExperimentArmConfig(name="candidate", provider=ProviderConfig(type="mock"))
        exp_config = ExperimentConfig(name="test_exp", control=control_arm, candidate=candidate_arm)

        mock_ctrl = MagicMock()
        mock_ctrl.complete.return_value = ModelResponse(
            output="Hello Alice", latency_ms=50.0, model="m", provider="p"
        )

        # Candidate output does NOT contain "Alice" -> assertion failure!
        mock_cand = MagicMock()
        mock_cand.complete.return_value = ModelResponse(
            output="Hello Bob", latency_ms=60.0, model="m", provider="p"
        )

        with patch("promptdrift.engine.experiment.create_provider") as mock_create:
            mock_create.side_effect = [mock_ctrl, mock_cand]
            report = run_experiment(config, exp_config, config_path)

        assert report.failed_pairs == 1
        assert report.passed_pairs == 0
        pair = report.pairs[0]
        assert pair.status == "FAIL"
        assert pair.control.status == "PASS"
        assert pair.candidate.status == "FAIL"
        assert len(pair.assertion_changes) > 0

    def test_incomparable_arm_on_provider_error(self, base_config):
        config, config_path = base_config

        control_arm = ExperimentArmConfig(name="control", provider=ProviderConfig(type="mock"))
        candidate_arm = ExperimentArmConfig(name="candidate", provider=ProviderConfig(type="mock"))
        exp_config = ExperimentConfig(name="test_exp", control=control_arm, candidate=candidate_arm)

        mock_ctrl = MagicMock()
        mock_ctrl.complete.side_effect = RuntimeError("Connection timed out")

        mock_cand = MagicMock()
        mock_cand.complete.return_value = ModelResponse(
            output="Hello Alice", latency_ms=50.0, model="m", provider="p"
        )

        with patch("promptdrift.engine.experiment.create_provider") as mock_create:
            mock_create.side_effect = [mock_ctrl, mock_cand]
            report = run_experiment(config, exp_config, config_path)

        assert report.incomparable_pairs == 1
        pair = report.pairs[0]
        assert pair.status == "INCOMPARABLE"
        assert pair.control.status == "ERROR"
        assert "Connection timed out" in pair.control.error

    def test_request_budget_exceeded_check(self, base_config):
        config, config_path = base_config

        control_arm = ExperimentArmConfig(name="control", provider=ProviderConfig(type="mock"))
        candidate_arm = ExperimentArmConfig(name="candidate", provider=ProviderConfig(type="mock"))
        # 1 test * 2 arms = 2 requests planned. Budget = 1 -> should raise
        exp_config = ExperimentConfig(
            name="budget_exp",
            control=control_arm,
            candidate=candidate_arm,
            request_budget=1,
        )

        with pytest.raises(ProviderBudgetExceededError, match="Planned experiment requests"):
            run_experiment(config, exp_config, config_path)

    def test_missing_usage_metadata_handled_gracefully(self, base_config):
        config, config_path = base_config

        control_arm = ExperimentArmConfig(name="control", provider=ProviderConfig(type="mock"))
        candidate_arm = ExperimentArmConfig(name="candidate", provider=ProviderConfig(type="mock"))
        exp_config = ExperimentConfig(name="test_exp", control=control_arm, candidate=candidate_arm)

        mock_ctrl = MagicMock()
        mock_ctrl.complete.return_value = ModelResponse(
            output="Hello Alice",
            latency_ms=10.0,
            input_tokens=None,
            output_tokens=None,
            estimated_cost_usd=None,
            model="m",
            provider="p",
        )

        mock_cand = MagicMock()
        mock_cand.complete.return_value = ModelResponse(
            output="Hello Alice",
            latency_ms=15.0,
            input_tokens=None,
            output_tokens=None,
            estimated_cost_usd=None,
            model="m",
            provider="p",
        )

        with patch("promptdrift.engine.experiment.create_provider") as mock_create:
            mock_create.side_effect = [mock_ctrl, mock_cand]
            report = run_experiment(config, exp_config, config_path)

        assert report.total_pairs == 1
        pair = report.pairs[0]
        assert pair.status == "PASS"
        assert pair.token_delta is None
        assert pair.cost_delta_usd is None
        assert pair.latency_delta_ms == 5.0


class TestCliExperiment:
    def test_cli_experiment_json_output(self, tmp_path: Path):
        prompt_file = tmp_path / "prompt.jinja"
        prompt_file.write_text("Test prompt", encoding="utf-8")

        config_file = tmp_path / "promptdrift.yaml"
        config_file.write_text(
            """
provider:
  type: mock
  model: mock-v1
tests:
  - id: t1
    prompt: prompt.jinja
    assertions:
      - type: contains
        value: "Test"
""",
            encoding="utf-8",
        )

        runner = CliRunner()
        result = runner.invoke(app, ["experiment", "-c", str(config_file), "--json"])
        assert result.exit_code == 0
        assert '"total_pairs": 1' in result.output
        assert '"passed_pairs": 1' in result.output
