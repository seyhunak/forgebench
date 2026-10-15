"""The provider contract. The benchmark runner depends only on this."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..schemas import BenchmarkCase, ProviderResponse


class ProviderError(RuntimeError):
    """Raised when a provider cannot produce a prediction at all."""


@runtime_checkable
class ModelProvider(Protocol):
    """Anything that can turn one case into one raw model response."""

    name: str
    model: str

    def predict(self, case: BenchmarkCase) -> ProviderResponse:
        """Return one structured prediction for ``case``.

        Implementations must never raise for a *bad model answer* (that is the
        runner's job to score); they raise :class:`ProviderError` only when no
        answer could be obtained (network failure, missing credentials, ...).
        """
        ...
