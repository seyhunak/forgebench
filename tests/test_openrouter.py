"""OpenRouter adapter: request shaping, response parsing and key handling.

Everything runs offline — ``urllib.request.urlopen`` is faked, so no network
and no API key is needed.
"""

from __future__ import annotations

import json
import urllib.error

import pytest

from forgebench.providers import openrouter
from forgebench.providers.base import ProviderError
from forgebench.providers.openrouter import OpenRouterProvider
from forgebench.schemas import Category

from .conftest import make_case


class _FakeResponse:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self._body = json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _capture(monkeypatch: pytest.MonkeyPatch, payload: dict) -> list[dict]:
    """Patch urlopen, returning the list that captures each request body."""
    sent: list[dict] = []

    def fake_urlopen(request, timeout=None):  # noqa: ARG001
        sent.append(json.loads(request.data.decode("utf-8")))
        return _FakeResponse(payload)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return sent


def _no_saved_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(openrouter, "get_value", lambda _name: None)


def test_missing_api_key_raises_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_saved_key(monkeypatch)
    with pytest.raises(ProviderError, match="OPENROUTER_API_KEY"):
        OpenRouterProvider(model="openai/gpt-4o")


def test_missing_model_raises_provider_error() -> None:
    with pytest.raises(ProviderError, match="model id"):
        OpenRouterProvider(model="", api_key="test-key")


def test_predict_parses_openai_compatible_response(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "model": "openai/gpt-4o",
        "choices": [{"message": {"role": "assistant", "content": '{"category": "matched"}'}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 7},
    }
    sent = _capture(monkeypatch, payload)
    provider = OpenRouterProvider(model="openai/gpt-4o", api_key="test-key")

    response = provider.predict(make_case("FIN-0001", Category.MATCHED))

    assert json.loads(response.content)["category"] == "matched"
    assert response.input_tokens == 12
    assert response.output_tokens == 7
    assert response.model == "openai/gpt-4o"
    assert sent[0]["model"] == "openai/gpt-4o"
    assert sent[0]["temperature"] == 0.0


def test_temperature_omitted_when_none(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"model": "x", "choices": [{"message": {"content": "{}"}}]}
    sent = _capture(monkeypatch, payload)
    provider = OpenRouterProvider(model="x", api_key="test-key", temperature=None)

    provider.predict_text("hello")

    assert "temperature" not in sent[0]
    assert sent[0]["messages"][-1]["content"] == "hello"


def test_namespaced_model_id_is_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "model": "meta-llama/llama-3.1-70b-instruct",
        "choices": [{"message": {"content": "{}"}}],
    }
    sent = _capture(monkeypatch, payload)
    provider = OpenRouterProvider(model="meta-llama/llama-3.1-70b-instruct", api_key="test-key")
    provider.predict_text("hi")
    assert sent[0]["model"] == "meta-llama/llama-3.1-70b-instruct"


def test_unexpected_shape_raises_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _capture(monkeypatch, {"error": "boom"})
    provider = OpenRouterProvider(model="x", api_key="test-key")
    with pytest.raises(ProviderError, match="unexpected response shape"):
        provider.predict_text("hi")


def test_list_form_content_is_flattened(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "model": "x",
        "choices": [
            {
                "message": {
                    "content": [
                        {"type": "text", "text": '{"category":'},
                        {"type": "text", "text": ' "matched"}'},
                    ]
                }
            }
        ],
    }
    _capture(monkeypatch, payload)
    provider = OpenRouterProvider(model="x", api_key="test-key")
    response = provider.predict_text("hi")
    assert json.loads(response.content)["category"] == "matched"


def test_retryable_classification() -> None:
    assert OpenRouterProvider._retryable(urllib.error.HTTPError("u", 429, "Too Many", {}, None))
    assert OpenRouterProvider._retryable(urllib.error.HTTPError("u", 503, "Unavailable", {}, None))
    assert not OpenRouterProvider._retryable(
        urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)
    )
    assert OpenRouterProvider._retryable(urllib.error.URLError("connection reset"))


def test_verify_api_key_accepts_200(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda request, timeout=None: _FakeResponse({}, 200)
    )
    accepted, detail = openrouter.verify_api_key("key")
    assert accepted is True
    assert "openrouter.ai" in detail


def test_verify_api_key_rejects_401(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_401(request, timeout=None):  # noqa: ARG001
        raise urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", raise_401)
    accepted, _detail = openrouter.verify_api_key("key")
    assert accepted is False


def test_verify_api_key_never_raises_on_network_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(request, timeout=None):  # noqa: ARG001
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    accepted, detail = openrouter.verify_api_key("key")
    assert accepted is None
    assert "offline" in detail.lower() or "could not verify" in detail


def test_list_models_returns_live_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = {
        "data": [
            {"id": "openai/gpt-4o", "name": "GPT-4o"},
            {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet"},
        ]
    }
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda request, timeout=None: _FakeResponse(catalog)
    )
    models = openrouter.list_models(api_key="key")
    assert [m["id"] for m in models] == ["openai/gpt-4o", "anthropic/claude-3.5-sonnet"]
