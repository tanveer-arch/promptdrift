import httpx
import pytest

from promptdrift.errors import ProviderError
from promptdrift.models.config import ProviderConfig
from promptdrift.providers.ollama import OllamaProvider
from promptdrift.providers.openai import OpenAIProvider


def test_openai_adapter_normalizes_response(monkeypatch):
    def fake_post(*args, **kwargs):
        assert kwargs["headers"]["Authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "hello"}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1},
            },
            request=httpx.Request("POST", "https://example.test"),
        )

    monkeypatch.setenv("TEST_OPENAI_KEY", "test-key")
    monkeypatch.setattr("promptdrift.providers.openai.httpx.post", fake_post)
    provider = OpenAIProvider(
        ProviderConfig(type="openai", model="test-model", api_key_env="TEST_OPENAI_KEY")
    )
    response = provider.complete("test", temperature=0, max_output_tokens=10)
    assert (response.output, response.input_tokens, response.output_tokens) == ("hello", 2, 1)


def test_openai_missing_key_is_safe(monkeypatch):
    monkeypatch.delenv("MISSING_KEY", raising=False)
    provider = OpenAIProvider(ProviderConfig(type="openai", model="x", api_key_env="MISSING_KEY"))
    with pytest.raises(ProviderError, match="MISSING_KEY is not set"):
        provider.complete("test", temperature=0, max_output_tokens=10)


def test_ollama_adapter_normalizes_response(monkeypatch):
    def fake_post(*args, **kwargs):
        return httpx.Response(
            200,
            json={"response": "local", "prompt_eval_count": 3, "eval_count": 1},
            request=httpx.Request("POST", "http://localhost:11434/api/generate"),
        )

    monkeypatch.setattr("promptdrift.providers.ollama.httpx.post", fake_post)
    provider = OllamaProvider(ProviderConfig(type="ollama", model="llama3.2"))
    response = provider.complete("test", temperature=0, max_output_tokens=10)
    assert (response.output, response.input_tokens, response.output_tokens) == ("local", 3, 1)
