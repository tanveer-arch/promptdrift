from .anthropic import AnthropicProvider
from .base import Provider
from .gemini import GeminiProvider
from .mock import MockProvider
from .ollama import OllamaProvider
from .openai import OpenAIProvider
from .resilience import ResilienceExecutor

__all__ = [
    "AnthropicProvider",
    "GeminiProvider",
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
        "gemini": GeminiProvider,
    }
    return providers[config.type](config)
