"""Capture configuration for production interaction recording."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CaptureConfig:
    """Configuration for the CaptureRecorder.

    All capture is opt-in: ``enabled`` defaults to False.
    Capture failures must never break the host application.
    """

    enabled: bool = False
    sample_rate: float = 1.0  # 0.0 = off, 1.0 = capture all
    max_interactions: int | None = None  # rolling retention cap
    retention_days: int | None = None  # time-based retention
    redact_patterns: list[str] = field(default_factory=list)
    redact_callback: Callable[[str], str] | None = None
    default_tags: list[str] = field(default_factory=list)
    db_path: Path | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.sample_rate <= 1.0:
            raise ValueError(f"sample_rate must be between 0.0 and 1.0, got {self.sample_rate}")
        if self.max_interactions is not None and self.max_interactions < 1:
            raise ValueError(f"max_interactions must be >= 1, got {self.max_interactions}")
        if self.retention_days is not None and self.retention_days < 1:
            raise ValueError(f"retention_days must be >= 1, got {self.retention_days}")
