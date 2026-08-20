"""Loading and validating promptdrift.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from .errors import ConfigError
from .models import Config


def load_config(path: str | Path = "promptdrift.yaml") -> tuple[Config, Path]:
    config_path = Path(path).resolve()
    if not config_path.is_file():
        raise ConfigError(f"Configuration file not found: {config_path}")
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {config_path.name}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("Configuration must be a YAML mapping at the top level.")
    try:
        return Config.model_validate(raw), config_path
    except ValidationError as exc:
        errors = "; ".join(
            f"{'.'.join(str(item) for item in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise ConfigError(f"Invalid configuration: {errors}") from exc
