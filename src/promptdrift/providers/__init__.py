from .anthropic import AnthropicProvider
from .base import Provider
from .mock import MockProvider
from .ollama import OllamaProvider
from .openai import OpenAIProvider
from .resilience import RequestBudget, ResilienceExecutor

__all__ = [
    "AnthropicProvider",
    "MockProvider",
    "OllamaProvider",
    "OpenAIProvider",
    "Provider",
    "RequestBudget",
    "ResilienceExecutor",
    "create_provider",
]


def create_provider(config, budget: RequestBudget | None = None):
    providers = {
        "openai": OpenAIProvider,
        "ollama": OllamaProvider,
        "mock": MockProvider,
        "anthropic": AnthropicProvider,
    }
    return providers[config.type](config, budget=budget)
