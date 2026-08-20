from .base import Provider
from .mock import MockProvider
from .ollama import OllamaProvider
from .openai import OpenAIProvider

__all__ = ["Provider", "MockProvider", "OllamaProvider", "OpenAIProvider", "create_provider"]


def create_provider(config):
    providers = {"openai": OpenAIProvider, "ollama": OllamaProvider, "mock": MockProvider}
    return providers[config.type](config)
