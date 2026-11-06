"""Offline tests for the Anthropic provider adapter."""

import json
from pathlib import Path

import httpx
import pytest

from promptdrift.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderTransportError,
)
from promptdrift.models.config import ProviderConfig
from promptdrift.providers import create_provider
from promptdrift.providers.anthropic import AnthropicProvider

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "anthropic"
API_KEY = "sk-ant-test-secret-12345"
POST_PATH = "promptdrift.providers.anthropic.httpx.post"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_provider(monkeypatch, **overrides) -> AnthropicProvider:
    monkeypatch.setenv("TEST_ANTHROPIC_KEY", API_KEY)
    config = ProviderConfig(
        type="anthropic",
        model="claude-test-model",
        api_key_env="TEST_ANTHROPIC_KEY",
        **overrides,
    )
    return AnthropicProvider(config)


def patch_post(monkeypatch, status=200, payload=None, content=None, captured=None):
    def fake_post(url, **kwargs):
        if captured is not None:
            captured["url"] = url
            captured["kwargs"] = kwargs
        request = httpx.Request("POST", url)
        if content is not None:
            return httpx.Response(status, content=content, request=request)
        return httpx.Response(status, json=payload, request=request)

    monkeypatch.setattr(POST_PATH, fake_post)


def run(provider: AnthropicProvider):
    return provider.complete("test prompt", temperature=0, max_output_tokens=10)


class TestAnthropicProvider:
    def test_normalizes_response(self, monkeypatch):
        captured: dict = {}
        patch_post(monkeypatch, payload=load_fixture("success.json"), captured=captured)
        response = run(make_provider(monkeypatch))

        assert response.output == "Hello PRIVATE_ANTHROPIC_OUTPUT_SENTINEL"
        assert response.input_tokens == 5
        assert response.output_tokens == 3
        assert response.provider == "anthropic"
        assert response.model == "claude-test-model"
        assert response.resolved_model == "claude-test-model"

        kwargs = captured["kwargs"]
        assert captured["url"] == "https://api.anthropic.com/v1/messages"
        assert kwargs["headers"]["x-api-key"] == API_KEY
        assert kwargs["headers"]["anthropic-version"] == "2023-06-01"
        assert kwargs["json"]["model"] == "claude-test-model"
        assert kwargs["json"]["max_tokens"] == 10
        assert kwargs["json"]["temperature"] == 0
        assert kwargs["json"]["messages"] == [{"role": "user", "content": "test prompt"}]

    def test_sends_system_prompt_when_configured(self, monkeypatch):
        captured: dict = {}
        patch_post(monkeypatch, payload=load_fixture("success.json"), captured=captured)
        run(make_provider(monkeypatch, system="You are terse."))
        assert captured["kwargs"]["json"]["system"] == "You are terse."

    def test_omits_system_prompt_when_not_configured(self, monkeypatch):
        captured: dict = {}
        patch_post(monkeypatch, payload=load_fixture("success.json"), captured=captured)
        run(make_provider(monkeypatch))
        assert "system" not in captured["kwargs"]["json"]

    def test_joins_text_blocks_and_ignores_other_blocks(self, monkeypatch):
        patch_post(monkeypatch, payload=load_fixture("multi_block.json"))
        response = run(make_provider(monkeypatch))
        assert response.output == "Hello, world"
        assert response.input_tokens == 7
        assert response.output_tokens == 4

    def test_custom_base_url(self, monkeypatch):
        captured: dict = {}
        patch_post(monkeypatch, payload=load_fixture("success.json"), captured=captured)
        run(make_provider(monkeypatch, base_url="https://proxy.test/v1/"))
        assert captured["url"] == "https://proxy.test/v1/messages"

    def test_missing_key_raises_safe_error(self, monkeypatch):
        monkeypatch.delenv("MISSING_KEY", raising=False)
        provider = AnthropicProvider(
            ProviderConfig(type="anthropic", model="x", api_key_env="MISSING_KEY")
        )
        with pytest.raises(ProviderAuthError, match="MISSING_KEY is not set"):
            run(provider)

    def test_uses_default_api_key_env(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        provider = AnthropicProvider(ProviderConfig(type="anthropic", model="x"))
        with pytest.raises(ProviderAuthError, match="ANTHROPIC_API_KEY is not set"):
            run(provider)

    @pytest.mark.parametrize(
        ("fixture", "status", "error_type"),
        [
            ("auth_error.json", 401, ProviderAuthError),
            ("auth_error.json", 403, ProviderAuthError),
            ("rate_limit.json", 429, ProviderRateLimitError),
            ("overloaded.json", 529, ProviderRateLimitError),
            ("server_error.json", 500, ProviderTransportError),
            ("bad_request.json", 400, ProviderResponseError),
        ],
    )
    def test_maps_http_errors_without_leaking(self, monkeypatch, fixture, status, error_type):
        patch_post(monkeypatch, status=status, payload=load_fixture(fixture))
        with pytest.raises(error_type) as exc_info:
            run(make_provider(monkeypatch))
        message = str(exc_info.value)
        assert message.startswith("Anthropic request failed")
        assert API_KEY not in message
        assert "PRIVATE_ERROR_BODY_SENTINEL" not in message

    def test_timeout_maps_to_timeout_error(self, monkeypatch):
        def fake_post(*args, **kwargs):
            raise httpx.ReadTimeout("slow")

        monkeypatch.setattr(POST_PATH, fake_post)
        with pytest.raises(ProviderTimeoutError):
            run(make_provider(monkeypatch))

    def test_connection_error_maps_to_transport_error(self, monkeypatch):
        def fake_post(*args, **kwargs):
            raise httpx.ConnectError("Connection refused")

        monkeypatch.setattr(POST_PATH, fake_post)
        with pytest.raises(ProviderTransportError) as exc_info:
            run(make_provider(monkeypatch))
        assert API_KEY not in str(exc_info.value)

    def test_invalid_json_maps_to_response_error(self, monkeypatch):
        patch_post(monkeypatch, content=b"not json")
        with pytest.raises(ProviderResponseError, match="invalid JSON"):
            run(make_provider(monkeypatch))

    def test_empty_content_maps_to_response_error(self, monkeypatch):
        patch_post(monkeypatch, payload=load_fixture("empty_content.json"))
        with pytest.raises(ProviderResponseError, match="no text content"):
            run(make_provider(monkeypatch))

    def test_retries_overloaded_then_succeeds(self, monkeypatch):
        monkeypatch.setenv("TEST_ANTHROPIC_KEY", API_KEY)
        responses = [
            (529, load_fixture("overloaded.json")),
            (200, load_fixture("success.json")),
        ]
        calls: list[str] = []

        def fake_post(url, **kwargs):
            status, payload = responses[len(calls)]
            calls.append(url)
            return httpx.Response(status, json=payload, request=httpx.Request("POST", url))

        monkeypatch.setattr(POST_PATH, fake_post)
        provider = AnthropicProvider(
            ProviderConfig(
                type="anthropic",
                model="claude-test-model",
                api_key_env="TEST_ANTHROPIC_KEY",
                max_retries=1,
            ),
            sleeper=lambda _seconds: None,
        )
        response = run(provider)
        assert len(calls) == 2
        assert response.output.startswith("Hello")

    def test_error_type_is_provider_error(self, monkeypatch):
        patch_post(monkeypatch, status=401, payload=load_fixture("auth_error.json"))
        with pytest.raises(ProviderError):
            run(make_provider(monkeypatch))


class TestAnthropicFactory:
    def test_creates_anthropic(self):
        provider = create_provider(ProviderConfig(type="anthropic", model="claude-test-model"))
        assert isinstance(provider, AnthropicProvider)


class TestAnthropicProvenance:
    def test_fingerprint_supports_anthropic(self):
        from promptdrift.engine.provenance import fingerprint
        from promptdrift.models.config import Config
        from promptdrift.models.test import TestCase

        test = TestCase(id="a", prompt="a.txt")
        config = Config(
            version=1,
            provider=ProviderConfig(type="anthropic", model="claude-test-model"),
            tests=[test],
        )
        result = fingerprint(config, test, "hello")
        assert result.provider_hash
