"""Provider adapters. Every adapter implements the same contract."""

from __future__ import annotations

from .base import ModelProvider, ProviderError
from .mistral import MistralProvider
from .mock import MockProvider

__all__ = ["ModelProvider", "ProviderError", "MockProvider", "MistralProvider", "build_provider"]


def build_provider(name: str, *, model: str, options: dict | None = None) -> ModelProvider:
    """Instantiate a provider by name. Unknown names fail loudly."""
    options = options or {}
    if name == "mock":
        return MockProvider(model=model, **options)
    if name == "mistral":
        return MistralProvider(model=model, **options)
    raise ProviderError(
        f"unknown provider '{name}'. Supported providers: mock, mistral. "
        "Add a new adapter in src/forgebench/providers/ instead of editing the runner."
    )
