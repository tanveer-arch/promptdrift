"""Offline coverage for Gemini response normalization and safety."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from promptdrift.cli import doctor
from promptdrift.engine.provenance import fingerprint
from promptdrift.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderTransportError,
)
from promptdrift.models.config import Config, ProviderConfig
from promptdrift.models.test import TestCase as PromptTestCase
from promptdrift.providers import create_provider
from promptdrift.providers.gemini import GeminiProvider

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "gemini"
API_KEY = "test-gemini-secret-key-12345"
POST_PATH = "promptdrift.providers.gemini.httpx.post"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_provider(monkeypatch, **overrides) -> GeminiProvider:
    monkeypatch.setenv("TEST_GEMINI_KEY", API_KEY)
    config = ProviderConfig(
        type="gemini",
        model="gemini-2.0-flash",
        api_key_env="TEST_GEMINI_KEY",
        **overrides,
    )
    return GeminiProvider(config)


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


def run(provider: GeminiProvider):
    return provider.complete("test prompt", temperature=0.7, max_output_tokens=100)


class TestGeminiProvider:
    def test_full_fixture_normalizes_supported_response(self, monkeypatch):
        captured: dict = {}
        patch_post(monkeypatch, payload=load_fixture("generate_full.json"), captured=captured)

        provider = make_provider(monkeypatch)
        response = run(provider)

        assert response.output == "Hello PRIVATE_GEMINI_OUTPUT_SENTINEL"
        assert response.input_tokens == 5
        assert response.output_tokens == 3
        assert response.model == "gemini-2.0-flash"
        assert response.provider == "gemini"
        assert response.resolved_model == "gemini-2.0-flash-001"
        assert response.system_fingerprint is None

        # Verify endpoint and header
        assert captured["url"] == (
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
        )
        kwargs = captured["kwargs"]
        assert kwargs["headers"]["x-goog-api-key"] == API_KEY
        # Verify no api key in url or query params
        assert "key=" not in captured["url"]
        assert API_KEY not in captured["url"]

        # Verify request payload
        assert kwargs["json"]["contents"] == [{"parts": [{"text": "test prompt"}]}]
        assert kwargs["json"]["generationConfig"] == {"temperature": 0.7, "maxOutputTokens": 100}

    def test_missing_model_version_maps_to_none(self, monkeypatch):
        patch_post(monkeypatch, payload=load_fixture("generate_no_model_version.json"))
        provider = make_provider(monkeypatch)
        response = run(provider)

        assert response.output == "Hello WITHOUT_MODEL_VERSION_SENTINEL"
        assert response.resolved_model is None
        assert response.input_tokens == 5
        assert response.output_tokens == 3

    def test_missing_usage_maps_to_none(self, monkeypatch):
        patch_post(monkeypatch, payload=load_fixture("generate_no_usage.json"))
        provider = make_provider(monkeypatch)
        response = run(provider)

        assert response.output == "Hello WITHOUT_USAGE_SENTINEL"
        assert response.input_tokens is None
        assert response.output_tokens is None
        assert response.resolved_model == "gemini-2.0-flash-001"

    def test_safety_blocked_response_fails_safely(self, monkeypatch):
        patch_post(monkeypatch, payload=load_fixture("generate_malformed.json"))
        provider = make_provider(monkeypatch)

        with pytest.raises(ProviderResponseError, match="blocked by safety filter: SAFETY"):
            run(provider)

    def test_missing_api_key_raises_auth_error(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("TEST_GEMINI_KEY", raising=False)
        config = ProviderConfig(type="gemini", model="gemini-2.0-flash")
        provider = GeminiProvider(config)

        with pytest.raises(ProviderAuthError, match="GEMINI_API_KEY is not set"):
            run(provider)

    def test_custom_api_key_env_and_google_api_key(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_API_KEY", "google-secret-val")
        config = ProviderConfig(
            type="gemini",
            model="gemini-2.0-flash",
            api_key_env="GOOGLE_API_KEY",
        )
        provider = GeminiProvider(config)
        captured: dict = {}
        patch_post(monkeypatch, payload=load_fixture("generate_full.json"), captured=captured)
        run(provider)
        assert captured["kwargs"]["headers"]["x-goog-api-key"] == "google-secret-val"

    def test_api_key_never_exposed_in_exception(self, monkeypatch):
        monkeypatch.setenv("TEST_GEMINI_KEY", "SUPER_SECRET_KEY_NEVER_LEAK")
        config = ProviderConfig(
            type="gemini",
            model="gemini-2.0-flash",
            api_key_env="TEST_GEMINI_KEY",
        )
        provider = GeminiProvider(config)

        def failing_post(url, **kwargs):
            raise httpx.ConnectError("Connection failed with internal details")

        monkeypatch.setattr(POST_PATH, failing_post)

        with pytest.raises(ProviderError) as exc_info:
            run(provider)

        assert "SUPER_SECRET_KEY_NEVER_LEAK" not in str(exc_info.value)

    def test_http_4xx_client_error(self, monkeypatch):
        def fake_post(url, **kwargs):
            req = httpx.Request("POST", url)
            resp = httpx.Response(400, request=req, text="Bad Request")
            raise httpx.HTTPStatusError("Bad Request", request=req, response=resp)

        monkeypatch.setattr(POST_PATH, fake_post)
        provider = make_provider(monkeypatch)

        with pytest.raises(ProviderResponseError, match="HTTPStatusError \\(400\\)"):
            run(provider)

    def test_http_401_403_auth_error(self, monkeypatch):
        def fake_post(url, **kwargs):
            req = httpx.Request("POST", url)
            resp = httpx.Response(401, request=req, text="Unauthorized")
            raise httpx.HTTPStatusError("Unauthorized", request=req, response=resp)

        monkeypatch.setattr(POST_PATH, fake_post)
        provider = make_provider(monkeypatch)

        with pytest.raises(ProviderAuthError, match="HTTPStatusError \\(401\\)"):
            run(provider)

    def test_http_429_rate_limit(self, monkeypatch):
        def fake_post(url, **kwargs):
            req = httpx.Request("POST", url)
            resp = httpx.Response(429, request=req, text="Too Many Requests")
            raise httpx.HTTPStatusError("Too Many Requests", request=req, response=resp)

        monkeypatch.setattr(POST_PATH, fake_post)
        provider = make_provider(monkeypatch)

        with pytest.raises(
            ProviderRateLimitError, match="HTTPStatusError \\(429 Too Many Requests\\)"
        ):
            run(provider)

    def test_http_5xx_server_error(self, monkeypatch):
        def fake_post(url, **kwargs):
            req = httpx.Request("POST", url)
            resp = httpx.Response(500, request=req, text="Internal Server Error")
            raise httpx.HTTPStatusError("Internal Server Error", request=req, response=resp)

        monkeypatch.setattr(POST_PATH, fake_post)
        provider = make_provider(monkeypatch)

        with pytest.raises(ProviderTransportError, match="HTTPStatusError \\(500\\)"):
            run(provider)

    def test_timeout_error(self, monkeypatch):
        def fake_post(url, **kwargs):
            raise httpx.ReadTimeout("timed out")

        monkeypatch.setattr(POST_PATH, fake_post)
        provider = make_provider(monkeypatch)

        with pytest.raises(ProviderTimeoutError, match="ReadTimeout"):
            run(provider)

    def test_connection_transport_error(self, monkeypatch):
        def fake_post(url, **kwargs):
            raise httpx.ConnectError("Failed to connect")

        monkeypatch.setattr(POST_PATH, fake_post)
        provider = make_provider(monkeypatch)

        with pytest.raises(ProviderTransportError, match="ConnectError"):
            run(provider)

    def test_invalid_json_response(self, monkeypatch):
        patch_post(monkeypatch, content=b"invalid json {")
        provider = make_provider(monkeypatch)

        with pytest.raises(ProviderResponseError, match="Gemini returned invalid JSON"):
            run(provider)

    def test_empty_candidates_error(self, monkeypatch):
        patch_post(monkeypatch, payload={"candidates": []})
        provider = make_provider(monkeypatch)

        with pytest.raises(ProviderResponseError, match="missing or empty candidates"):
            run(provider)

    def test_missing_content_or_parts(self, monkeypatch):
        patch_post(monkeypatch, payload={"candidates": [{}]})
        provider = make_provider(monkeypatch)

        with pytest.raises(ProviderResponseError, match="Gemini candidate missing content"):
            run(provider)

        patch_post(monkeypatch, payload={"candidates": [{"content": {}}]})
        with pytest.raises(ProviderResponseError, match="Gemini content missing or empty parts"):
            run(provider)

    def test_non_string_part_content(self, monkeypatch):
        patch_post(monkeypatch, payload=load_fixture("generate_non_string.json"))
        provider = make_provider(monkeypatch)

        with pytest.raises(ProviderResponseError, match="Gemini part missing text"):
            run(provider)

        patch_post(
            monkeypatch,
            payload={"candidates": [{"content": {"parts": [{"text": 123}]}}]},
        )
        with pytest.raises(ProviderResponseError, match="Gemini part text is not a string"):
            run(provider)

    def test_system_prompt_inclusion(self, monkeypatch):
        captured: dict = {}
        patch_post(monkeypatch, payload=load_fixture("generate_full.json"), captured=captured)
        provider = make_provider(monkeypatch, system="You are an expert.")
        run(provider)

        assert captured["kwargs"]["json"]["systemInstruction"] == {
            "parts": [{"text": "You are an expert."}]
        }

    def test_custom_base_url(self, monkeypatch):
        captured: dict = {}
        patch_post(monkeypatch, payload=load_fixture("generate_full.json"), captured=captured)
        provider = make_provider(monkeypatch, base_url="https://custom.gemini.proxy/v1")
        run(provider)

        assert captured["url"] == (
            "https://custom.gemini.proxy/v1/v1beta/models/gemini-2.0-flash:generateContent"
        )

    def test_factory_registration(self):
        config = ProviderConfig(type="gemini", model="gemini-2.0-flash")
        provider = create_provider(config)
        assert isinstance(provider, GeminiProvider)
        assert provider.config.type == "gemini"

    def test_provenance_fingerprinting(self):
        config = Config(
            provider=ProviderConfig(type="gemini", model="gemini-2.0-flash"),
            tests=[
                PromptTestCase(
                    id="test_gemini",
                    prompt="Hello gemini",
                )
            ],
        )
        prov = fingerprint(config, config.tests[0], "Hello gemini")
        assert prov.provider_hash is not None
        assert prov.input_hash is not None

    def test_doctor_key_env_defaults(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GEMINI_API_KEY", "test-doctor-key")
        config_file = tmp_path / "promptdrift.yaml"
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Hello doctor", encoding="utf-8")

        config_content = (
            "version: 1\n"
            "provider:\n"
            "  type: gemini\n"
            "  model: gemini-2.0-flash\n"
            "tests:\n"
            "  - id: t1\n"
            "    prompt: prompt.txt\n"
        )
        config_file.write_text(config_content, encoding="utf-8")

        # doctor should find GEMINI_API_KEY and return cleanly without raising Exit
        doctor(config=config_file)

        # When GEMINI_API_KEY is missing, doctor should fail with exit code 2
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        import typer

        with pytest.raises(typer.Exit) as exit_err:
            doctor(config=config_file)
        assert exit_err.value.exit_code == 2
