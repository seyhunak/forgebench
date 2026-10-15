"""Estimated inference pricing.

Prices below are **historical example values** transcribed for estimation
only. API pricing changes; verify against https://mistral.ai/pricing (or your
provider's current price list) before publishing any cost claim, and always
label results with the measurement date. Estimates use recorded token usage
when the provider returned it, and a chars/4 heuristic otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    input_per_mtok: float
    output_per_mtok: float
    as_of: str
    note: str = ""


_PRICES: dict[str, ModelPrice] = {
    "open-mistral-7b": ModelPrice(0.15, 0.15, "2024-07 (historical)"),
    "open-mistral-nemo": ModelPrice(0.15, 0.15, "2024-07 (historical)"),
    "mistral-small-latest": ModelPrice(0.20, 0.60, "2024-07 (historical)"),
    "mistral-medium-latest": ModelPrice(0.40, 1.20, "2024-07 (historical)"),
    "mistral-large-latest": ModelPrice(2.00, 6.00, "2024-07 (historical)"),
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
