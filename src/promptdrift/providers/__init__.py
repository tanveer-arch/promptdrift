from .anthropic import AnthropicProvider
from .base import Provider
from .mock import MockProvider
from .ollama import OllamaProvider
from .openai import OpenAIProvider
from .resilience import ResilienceExecutor

__all__ = [
    "AnthropicProvider",
    "MockProvider",
    "OllamaProvider",
    "OpenAIProvider",
    "Provider",
    "ResilienceExecutor",
    "create_provider",
]


def create_provider(config):
    providers = {
        "openai": OpenAIProvider,
        "ollama": OllamaProvider,
        "mock": MockProvider,
        "anthropic": AnthropicProvider,
    }
    return providers[config.type](config)
