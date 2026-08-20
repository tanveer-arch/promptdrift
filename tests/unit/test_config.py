from pathlib import Path

import pytest

from promptdrift.config import load_config
from promptdrift.errors import ConfigError


def test_config_is_strict(tmp_path: Path):
    path = tmp_path / "promptdrift.yaml"
    path.write_text("version: 1\nprovider: {type: mock}\ntests: []\nunknown: true\n")
    with pytest.raises(ConfigError, match="unknown"):
        load_config(path)


def test_config_loads_valid_suite(tmp_path: Path):
    path = tmp_path / "promptdrift.yaml"
    path.write_text("version: 1\nprovider: {type: mock}\ntests:\n  - id: hello\n    prompt: hello.txt\n")
    config, _ = load_config(path)
    assert config.provider.type == "mock"


def test_unimplemented_evaluator_is_rejected(tmp_path: Path):
    path = tmp_path / "promptdrift.yaml"
    path.write_text(
        "version: 1\nprovider: {type: mock}\ntests:\n"
        "  - id: hello\n    prompt: hello.txt\n"
        "    evaluators: [{type: semantic_similarity, threshold: 0.9}]\n"
    )
    with pytest.raises(ConfigError, match="not available"):
        load_config(path)
