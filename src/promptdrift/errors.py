"""Exceptions with safe, actionable messages for PromptDrift users."""


class PromptDriftError(Exception):
    """Base class for expected application errors."""


class ConfigError(PromptDriftError):
    """Configuration is invalid or unavailable."""


class TemplateError(PromptDriftError):
    """A prompt template cannot be safely rendered."""


class ProviderError(PromptDriftError):
    """A provider request could not be completed."""


class EvaluationError(PromptDriftError):
    """An evaluator received invalid input."""


class BaselineError(PromptDriftError):
    """A baseline could not be read or safely written."""
