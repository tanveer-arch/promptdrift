"""Production capture subpackage.

Provides :class:`CaptureRecorder` for provider-agnostic interaction recording
and :class:`CaptureConfig` for opt-in configuration.
"""

from promptdrift.capture.config import CaptureConfig
from promptdrift.capture.recorder import CaptureRecorder

__all__ = ["CaptureConfig", "CaptureRecorder"]
