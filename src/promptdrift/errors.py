"""Exceptions with safe, actionable messages for PromptDrift users."""


class PromptDriftError(Exception):
    """Base class for expected application errors."""


class ConfigError(PromptDriftError):
    """Configuration is invalid or unavailable."""


class TemplateError(PromptDriftError):
    """A prompt template cannot be safely rendered."""


class ProviderError(PromptDriftError):
    """A provider request could not be completed."""


class ProviderAuthError(ProviderError):
    """Authentication or authorization failure with the provider."""


class ProviderRateLimitError(ProviderError):
    """Rate limit or concurrency quota exceeded with the provider."""


class ProviderTimeoutError(ProviderError):
    """Provider request timed out."""


class ProviderConnectionError(ProviderError):
    """Network connection or unreachable host error with the provider."""


class ProviderResponseError(ProviderError):
    """Provider returned a malformed or unexpected response payload."""


class EvaluationError(PromptDriftError):
    """An evaluator received invalid input."""


class BaselineError(PromptDriftError):
    """A baseline could not be read or safely written."""
