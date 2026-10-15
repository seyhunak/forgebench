"""Estimated inference pricing.

Prices come from https://mistral.ai/inference/pricing (Standard tier, USD,
per million tokens) as of the `as_of` date on each entry. API pricing changes
without notice: verify before publishing any cost claim, and always label
results with the measurement date. Estimates use recorded token usage when
the provider returned it, and a chars/4 heuristic otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    input_per_mtok: float
    output_per_mtok: float
    as_of: str
    note: str = ""


_VERIFIED = "2026-10-15"

#: (model id, input $/Mtok, output $/Mtok, note) — Standard tier, USD.
_CURRENT = (
    ("ministral-8b-2512", 0.15, 0.15, "Ministral 3 8B, Apache-2.0"),
    ("ministral-3-8b-25-12", 0.15, 0.15, "Ministral 3 8B (page-slug alias)"),
    ("ministral-3b-2512", 0.10, 0.10, "Ministral 3 3B, Apache-2.0"),
    ("ministral-3-3b-25-12", 0.10, 0.10, "Ministral 3 3B (page-slug alias)"),
    ("ministral-14b-2512", 0.20, 0.20, "Ministral 3 14B, Apache-2.0"),
    ("ministral-3-14b-25-12", 0.20, 0.20, "Ministral 3 14B (page-slug alias)"),
    ("mistral-small-4-0-26-03", 0.15, 0.60, "Mistral Small 4, Apache-2.0"),
    ("mistral-large-3-25-12", 0.50, 1.50, "Mistral Large 3, Apache-2.0"),
    ("mistral-large-4-0", 0.68, 2.09, "Mistral Large 4 (listed sale price)"),
    ("mistral-medium-3-5-26-04", 1.50, 7.50, "Mistral Medium 3.5, Modified MIT"),
)

#: Retired / historical entries so old manifests still estimate sensibly.
_HISTORICAL = (
    ("open-mistral-7b", 0.15, 0.15, "retired 2025-03; historical price"),
    ("mistral-small-latest", 0.20, 0.60, "alias; verify current target"),
    ("mistral-large-latest", 2.00, 6.00, "alias; verify current target"),
)

_PRICES: dict[str, ModelPrice] = {
    **{name: ModelPrice(i, o, _VERIFIED, note) for name, i, o, note in _CURRENT},
    **{name: ModelPrice(i, o, "historical", note) for name, i, o, note in _HISTORICAL},
    "rule-mock-v1": ModelPrice(0.0, 0.0, "n/a", "mock provider incurs no API cost"),
}

DEFAULT_PRICE = ModelPrice(
    0.0, 0.0, "unknown", "no price table entry; cost reported as 0 with a warning"
)


def price_for(model: str) -> ModelPrice:
    if not model:
        return DEFAULT_PRICE
    return _PRICES.get(model) or _PRICES.get(model.split(":")[-1]) or DEFAULT_PRICE


def register_price(model: str, price: ModelPrice) -> None:
    """Allow experiments to override or extend the table (e.g. custom endpoints)."""
    _PRICES[model] = price
