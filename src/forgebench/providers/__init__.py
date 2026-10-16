"""Provider adapters. Every adapter implements the same contract."""

from __future__ import annotations

from .anthropic import AnthropicProvider
from .base import ModelProvider, ProviderError
from .google import GoogleProvider
from .mistral import MistralProvider
from .mock import MockProvider
from .openai import OpenAIProvider

__all__ = [
    "ModelProvider",
    "ProviderError",
    "MockProvider",
    "MistralProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "GoogleProvider",
    "build_provider",
    "task_provider_options",
]


def task_provider_options(
    name: str,
    *,
    output_schema: list[dict] | None = None,
    system_prompt: str | None = None,
) -> dict:
    """Constructor options that are safe to forward for a custom-task provider.

    The mock adapter absorbs the task output schema through ``**kwargs`` so it
    can fabricate schema-shaped JSON. The real adapters reject unknown keyword
    arguments, so they receive only ``system_prompt`` — the schema still reaches
    the model as prompt text. Leaking the schema knobs to a real provider raised
    ``TypeError`` at run start.
    """
    if name == "mock":
        return {"system_prompt": system_prompt, "output_schema": output_schema or []}
    return {"system_prompt": system_prompt} if system_prompt else {}


def build_provider(name: str, *, model: str, options: dict | None = None) -> ModelProvider:
    """Instantiate a provider by name. Unknown names fail loudly."""
    options = options or {}
    if name == "mock":
        return MockProvider(model=model, **options)
    if name == "mistral":
        return MistralProvider(model=model, **options)
    if name == "openai":
        return OpenAIProvider(model=model, **options)
    if name == "anthropic":
        return AnthropicProvider(model=model, **options)
    if name == "google":
        return GoogleProvider(model=model, **options)
    raise ProviderError(
        f"unknown provider '{name}'. Supported providers: mock, mistral, openai, "
        "anthropic, google. Add a new adapter in src/forgebench/providers/ "
        "instead of editing the runner."
    )
