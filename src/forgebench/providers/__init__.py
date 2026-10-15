"""Provider adapters. Every adapter implements the same contract."""

from __future__ import annotations

from .base import ModelProvider, ProviderError
from .mistral import MistralProvider
from .mock import MockProvider
from .openai import OpenAIProvider
from .anthropic import AnthropicProvider
from .google import GoogleProvider

__all__ = [
    "ModelProvider",
    "ProviderError",
    "MockProvider",
    "MistralProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "GoogleProvider",
    "build_provider",
]


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
