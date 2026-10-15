"""Estimated inference pricing.

Prices adopted from https://llmgateway.io/models (columns: Provider | Model ID |
Input $/M | Output $/M | Cache Read $/M) as of the `as_of` date on each entry.
API pricing changes without notice: verify before publishing any cost claim,
and always label results with the measurement date. Estimates use recorded
token usage when the provider returned it, and a chars/4 heuristic otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    provider: str  # titleized provider name (e.g. "OpenAI")
    model_id: str  # model identifier (e.g. "gpt-4o")
    input_per_mtok: float  # USD per million input tokens
    output_per_mtok: float  # USD per million output tokens
    cache_read_per_mtok: float | None  # USD per million cached-read tokens, or None
    as_of: str
    note: str = ""


_VERIFIED = "2026-10-15"

#: (provider, model id, input $/M, output $/M, cache read $/M, note) — USD.
_CURRENT = (
    # OpenAI
    ("OpenAI", "gpt-5", 1.25, 10.00, None, "OpenAI GPT-5"),
    ("OpenAI", "gpt-5-mini", 0.25, 2.00, None, "OpenAI GPT-5 mini"),
    ("OpenAI", "gpt-5-nano", 0.05, 0.40, None, "OpenAI GPT-5 nano"),
    ("OpenAI", "gpt-4.1", 2.00, 8.00, None, "OpenAI GPT-4.1"),
    ("OpenAI", "gpt-4.1-mini", 0.40, 1.60, None, "OpenAI GPT-4.1 mini"),
    ("OpenAI", "gpt-4.1-nano", 0.10, 0.40, None, "OpenAI GPT-4.1 nano"),
    ("OpenAI", "gpt-4o", 2.50, 10.00, None, "OpenAI GPT-4o"),
    ("OpenAI", "gpt-4o-mini", 0.15, 0.60, None, "OpenAI GPT-4o mini"),
    ("OpenAI", "o1", 15.00, 60.00, None, "OpenAI o1"),
    ("OpenAI", "o1-mini", 1.10, 4.40, None, "OpenAI o1 mini"),
    ("OpenAI", "o3-mini", 1.10, 4.40, None, "OpenAI o3 mini"),
    # Anthropic
    ("Anthropic", "claude-4-opus", 15.00, 75.00, None, "Anthropic Claude 4 Opus"),
    ("Anthropic", "claude-4-sonnet", 3.00, 15.00, None, "Anthropic Claude 4 Sonnet"),
    ("Anthropic", "claude-3-5-sonnet", 3.00, 15.00, 0.10, "Anthropic Claude 3.5 Sonnet"),
    ("Anthropic", "claude-3-opus", 15.00, 75.00, None, "Anthropic Claude 3 Opus"),
    ("Anthropic", "claude-3-haiku", 0.25, 1.25, 0.01, "Anthropic Claude 3 Haiku"),
    # Google
    ("Google", "gemini-2.5-pro", 1.25, 10.00, None, "Google Gemini 2.5 Pro"),
    ("Google", "gemini-2.5-flash", 0.15, 0.60, None, "Google Gemini 2.5 Flash"),
    ("Google", "gemini-2.0-flash", 0.10, 0.40, None, "Google Gemini 2.0 Flash"),
    ("Google", "gemini-1.5-pro", 1.25, 5.00, None, "Google Gemini 1.5 Pro"),
    ("Google", "gemini-1.5-flash", 0.075, 0.30, None, "Google Gemini 1.5 Flash"),
    # Mistral
    ("Mistral", "ministral-8b-2512", 0.15, 0.15, None, "Ministral 3 8B, Apache-2.0"),
    ("Mistral", "ministral-3b-2512", 0.10, 0.10, None, "Ministral 3 3B, Apache-2.0"),
    ("Mistral", "ministral-14b-2512", 0.20, 0.20, None, "Ministral 3 14B, Apache-2.0"),
    ("Mistral", "mistral-small-4-0-26-03", 0.15, 0.60, None, "Mistral Small 4, Apache-2.0"),
    ("Mistral", "mistral-large-3-25-12", 0.50, 1.50, None, "Mistral Large 3, Apache-2.0"),
    ("Mistral", "mistral-large-4-0", 0.68, 2.09, 0.14, "Mistral Large 4 (listed sale price)"),
    ("Mistral", "mistral-medium-3-5-26-04", 1.50, 7.50, None, "Mistral Medium 3.5, Modified MIT"),
)

#: Retired / historical entries so old manifests still estimate sensibly.
_HISTORICAL = (
    ("Mistral", "open-mistral-7b", 0.15, 0.15, None, "retired 2025-03; historical price"),
    ("Mistral", "mistral-small-latest", 0.20, 0.60, None, "alias; verify current target"),
    ("Mistral", "mistral-large-latest", 2.00, 6.00, None, "alias; verify current target"),
)

_PRICES: dict[str, ModelPrice] = {}
for provider, model_id, inp, outp, cache, note in _CURRENT:
    _PRICES[model_id] = ModelPrice(
        provider=provider,
        model_id=model_id,
        input_per_mtok=inp,
        output_per_mtok=outp,
        cache_read_per_mtok=cache,
        as_of=_VERIFIED,
        note=note,
    )
for provider, model_id, inp, outp, cache, note in _HISTORICAL:
    _PRICES[model_id] = ModelPrice(
        provider=provider,
        model_id=model_id,
        input_per_mtok=inp,
        output_per_mtok=outp,
        cache_read_per_mtok=cache,
        as_of="historical",
        note=note,
    )
_PRICES["rule-mock-v1"] = ModelPrice(
    provider="Mock",
    model_id="rule-mock-v1",
    input_per_mtok=0.0,
    output_per_mtok=0.0,
    cache_read_per_mtok=None,
    as_of="n/a",
    note="mock provider incurs no API cost",
)

DEFAULT_PRICE = ModelPrice(
    provider="Unknown",
    model_id="unknown",
    input_per_mtok=0.0,
    output_per_mtok=0.0,
    cache_read_per_mtok=None,
    as_of="unknown",
    note="no price table entry; cost reported as 0 with a warning",
)


def price_for(model: str) -> ModelPrice:
    if not model:
        return DEFAULT_PRICE
    return _PRICES.get(model) or _PRICES.get(model.split(":")[-1]) or DEFAULT_PRICE


def register_price(
    model: str,
    provider: str,
    *,
    input_per_mtok: float,
    output_per_mtok: float,
    cache_read_per_mtok: float | None = None,
    as_of: str = _VERIFIED,
    note: str = "",
) -> None:
    """Allow experiments to override or extend the table (e.g. custom endpoints)."""
    _PRICES[model] = ModelPrice(
        provider=provider,
        model_id=model,
        input_per_mtok=input_per_mtok,
        output_per_mtok=output_per_mtok,
        cache_read_per_mtok=cache_read_per_mtok,
        as_of=as_of,
        note=note,
    )


def list_prices() -> list[ModelPrice]:
    """Return all known model prices, sorted by provider then model id."""
    return sorted(_PRICES.values(), key=lambda p: (p.provider, p.model_id))
