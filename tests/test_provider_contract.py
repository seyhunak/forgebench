"""Provider contract tests: every adapter behaves the same way."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from forgebench.providers import (
    AnthropicProvider,
    GoogleProvider,
    MistralProvider,
    MockProvider,
    OpenAIProvider,
    OpenRouterProvider,
    build_provider,
    task_provider_options,
)
from forgebench.providers.base import ModelProvider, ProviderError
from forgebench.schemas import Category

from .conftest import make_case

ALL_CATEGORIES = list(Category)

REAL_PROVIDERS = {
    "mistral": MistralProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "google": GoogleProvider,
    "openrouter": OpenRouterProvider,
}


@pytest.mark.parametrize("name", sorted(REAL_PROVIDERS))
def test_task_provider_options_are_accepted_by_real_adapters(name: str) -> None:
    """Real adapters must never receive kwargs they do not declare.

    Passing the task schema knobs straight through raised
    ``MistralProvider.__init__() got an unexpected keyword argument
    'input_fields'`` the moment a task ran on a real provider.
    """
    options = task_provider_options(
        name, output_schema=[{"name": "sentiment"}], system_prompt="be terse"
    )
    params = inspect.signature(REAL_PROVIDERS[name].__init__).parameters
    accepts_kwargs = any(p.kind is p.VAR_KEYWORD for p in params.values())
    unknown = [k for k in options if k not in params]
    assert not unknown or accepts_kwargs, f"{name} would reject {unknown}"


def test_task_provider_options_keep_schema_for_mock_only() -> None:
    schema = [{"name": "sentiment", "type": "enum"}]
    mock = task_provider_options("mock", output_schema=schema, system_prompt="sys")
    assert mock["output_schema"] == schema

    real = task_provider_options("mistral", output_schema=schema, system_prompt="sys")
    assert real == {"system_prompt": "sys"}
    assert "output_schema" not in real


def test_task_provider_options_for_real_provider_omit_blank_system_prompt() -> None:
    assert task_provider_options("openai", system_prompt=None) == {}


@pytest.mark.parametrize("category", [c for c in ALL_CATEGORIES if c is not Category.AMBIGUOUS])
def test_mock_classifies_every_family_correctly_with_zero_defects(category: Category) -> None:
    case = make_case("FIN-0001", category)
    provider = MockProvider(defect_rate=0.0)
    response = provider.predict(case)
    payload = json.loads(response.content)
    assert payload["category"] == category.value
    assert payload["requires_review"] == (category is not Category.MATCHED)


def test_mock_cannot_resolve_ambiguous_by_design() -> None:
    """Documented limitation: the rule engine has no path to 'ambiguous'."""
    case = make_case("FIN-0001", Category.AMBIGUOUS)
    payload = json.loads(MockProvider().predict(case).content)
    assert payload["category"] != Category.AMBIGUOUS.value


def test_mock_implements_the_protocol() -> None:
    assert isinstance(MockProvider(), ModelProvider)


def test_mock_is_deterministic() -> None:
    case = make_case("FIN-0001", Category.AMBIGUOUS)
    provider = MockProvider(defect_rate=0.3, invalid_rate=0.3, seed=7)
    first, second = provider.predict(case), provider.predict(case)
    assert first.content == second.content
    assert first.latency_ms == second.latency_ms


def test_mock_defect_rate_one_never_matches_its_own_clean_answer() -> None:
    for category in ALL_CATEGORIES:
        case = make_case("FIN-0001", category)
        clean = MockProvider(defect_rate=0.0, seed=1).category_for(case)
        dirty = MockProvider(defect_rate=1.0, seed=1).category_for(case)
        assert dirty is not clean


def test_mock_invalid_rate_one_breaks_the_contract_on_purpose() -> None:
    case = make_case("FIN-0001", Category.MATCHED)
    provider = MockProvider(invalid_rate=1.0)
    content = provider.predict(case).content
    with pytest.raises(json.JSONDecodeError):
        json.loads(content)


def test_mock_rejects_impossible_rates() -> None:
    with pytest.raises(ProviderError):
        MockProvider(defect_rate=1.5)
    with pytest.raises(ProviderError):
        MockProvider(invalid_rate=-0.1)


def test_build_provider_unknown_name_fails_loudly() -> None:
    with pytest.raises(ProviderError, match="unknown provider"):
        build_provider("definitely-not-a-provider", model="x")


def test_mistral_requires_an_api_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    # get_value falls back to the nearest .env, so run where there is none —
    # a key saved through `forgebench set-key` or the Setup view must not make
    # this test pass or fail depending on the developer's local credentials.
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ProviderError, match="MISTRAL_API_KEY"):
        MistralProvider(model="open-mistral-7b")


def test_ollama_key_storage_does_not_imply_run_support() -> None:
    """Setup/set-key save OLLAMA_API_KEY, but running needs an adapter that does not exist yet."""
    with pytest.raises(ProviderError, match="unknown provider"):
        build_provider("ollama", model="llama3.1")


def test_mistral_retry_policy_only_retries_operational_failures() -> None:
    rate_limit = type("RateLimitError", (Exception,), {})
    assert MistralProvider._retryable(rate_limit("429 too many requests")) is True
    assert MistralProvider._retryable(Exception("gateway timeout")) is True
    assert MistralProvider._retryable(Exception("invalid model id")) is False
