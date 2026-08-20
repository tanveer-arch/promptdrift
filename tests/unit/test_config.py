"""Tests for configuration loading and validation."""
from pathlib import Path

import pytest

from promptdrift.config import load_config
from promptdrift.errors import ConfigError


class TestConfigLoading:
    def test_loads_valid_minimal_config(self, tmp_path):
        path = tmp_path / "promptdrift.yaml"
        path.write_text("version: 1\nprovider: {type: mock}\ntests:\n  - id: hello\n    prompt: hello.txt\n")
        config, config_path = load_config(path)
        assert config.provider.type == "mock"
        assert config.version == 1
        assert len(config.tests) == 1

    def test_loads_full_config(self, tmp_path):
        path = tmp_path / "promptdrift.yaml"
        path.write_text(
            "version: 1\nprovider:\n  type: openai\n  model: gpt-4.1-mini\n  api_key_env: MY_KEY\n"
            "defaults:\n  temperature: 0.5\n  max_output_tokens: 200\n"
            "baseline:\n  path: my-baseline.json\n  store_raw_output: true\n"
            "tests:\n  - id: test1\n    prompt: p.txt\n    assertions:\n      - {type: contains, value: hello}\n"
        )
        config, _ = load_config(path)
        assert config.provider.model == "gpt-4.1-mini"
        assert config.defaults.temperature == 0.5
        assert config.defaults.max_output_tokens == 200
        assert config.baseline.path == "my-baseline.json"
        assert config.baseline.store_raw_output is True

    def test_applies_defaults(self, tmp_path):
        path = tmp_path / "promptdrift.yaml"
        path.write_text("version: 1\nprovider: {type: mock}\ntests:\n  - id: hello\n    prompt: p.txt\n")
        config, _ = load_config(path)
        assert config.defaults.temperature == 0
        assert config.defaults.max_output_tokens == 500
        assert config.baseline.path == "promptdrift.baseline.json"


class TestConfigValidation:
    def test_rejects_unknown_fields(self, tmp_path):
        path = tmp_path / "promptdrift.yaml"
        path.write_text("version: 1\nprovider: {type: mock}\ntests: []\nunknown: true\n")
        with pytest.raises(ConfigError, match="unknown"):
            load_config(path)

    def test_rejects_duplicate_test_ids(self, tmp_path):
        path = tmp_path / "promptdrift.yaml"
        path.write_text(
            "version: 1\nprovider: {type: mock}\n"
            "tests:\n  - id: same\n    prompt: a.txt\n  - id: same\n    prompt: b.txt\n"
        )
        with pytest.raises(ConfigError, match="unique"):
            load_config(path)

    def test_rejects_empty_test_list(self, tmp_path):
        path = tmp_path / "promptdrift.yaml"
        path.write_text("version: 1\nprovider: {type: mock}\ntests: []\n")
        with pytest.raises(ConfigError):
            load_config(path)

    def test_rejects_invalid_provider_type(self, tmp_path):
        path = tmp_path / "promptdrift.yaml"
        path.write_text("version: 1\nprovider: {type: anthropic}\ntests:\n  - id: a\n    prompt: a.txt\n")
        with pytest.raises(ConfigError):
            load_config(path)

    def test_rejects_temperature_out_of_range(self, tmp_path):
        path = tmp_path / "promptdrift.yaml"
        path.write_text(
            "version: 1\nprovider: {type: mock}\ndefaults: {temperature: 5}\n"
            "tests:\n  - id: a\n    prompt: a.txt\n"
        )
        with pytest.raises(ConfigError):
            load_config(path)

    def test_rejects_unimplemented_evaluator(self, tmp_path):
        path = tmp_path / "promptdrift.yaml"
        path.write_text(
            "version: 1\nprovider: {type: mock}\ntests:\n"
            "  - id: hello\n    prompt: hello.txt\n"
            "    evaluators: [{type: semantic_similarity, threshold: 0.9}]\n"
        )
        with pytest.raises(ConfigError, match="not available"):
            load_config(path)

    def test_rejects_invalid_test_id_format(self, tmp_path):
        path = tmp_path / "promptdrift.yaml"
        path.write_text("version: 1\nprovider: {type: mock}\ntests:\n  - id: 'has spaces'\n    prompt: a.txt\n")
        with pytest.raises(ConfigError):
            load_config(path)


class TestConfigErrors:
    def test_missing_file(self, tmp_path):
        with pytest.raises(ConfigError, match="not found"):
            load_config(tmp_path / "nonexistent.yaml")

    def test_invalid_yaml(self, tmp_path):
        path = tmp_path / "promptdrift.yaml"
        path.write_text(": :\n  - [broken: yaml\n")
        with pytest.raises(ConfigError, match="Invalid YAML"):
            load_config(path)

    def test_non_mapping_yaml(self, tmp_path):
        path = tmp_path / "promptdrift.yaml"
        path.write_text("- just\n- a\n- list\n")
        with pytest.raises(ConfigError, match="mapping"):
            load_config(path)


class TestPathResolution:
    def test_resolves_relative_paths(self, tmp_path):
        path = tmp_path / "promptdrift.yaml"
        path.write_text("version: 1\nprovider: {type: mock}\ntests:\n  - id: a\n    prompt: prompts/test.txt\n")
        config, config_path = load_config(path)
        resolved = config.resolve_path(config_path, "prompts/test.txt")
        assert resolved == tmp_path / "prompts" / "test.txt"

    def test_absolute_paths_unchanged(self, tmp_path):
        abs_path_str = Path(tmp_path.anchor, "abs", "path.txt").as_posix()
        path = tmp_path / "promptdrift.yaml"
        path.write_text(f"version: 1\nprovider: {{type: mock}}\ntests:\n  - id: a\n    prompt: {abs_path_str}\n")
        config, config_path = load_config(path)
        resolved = config.resolve_path(config_path, abs_path_str)
        assert resolved == Path(abs_path_str)
