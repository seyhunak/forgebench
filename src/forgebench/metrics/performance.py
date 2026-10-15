"""Operational metrics: latency distribution and estimated inference cost."""

from __future__ import annotations

from typing import Any

from ..schemas import PredictionRecord
from .pricing import price_for


def percentile(values: list[float], quantile: float) -> float:
    """Linear-interpolation percentile of a non-empty list. Deterministic."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = quantile * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def latency_summary(records: list[PredictionRecord]) -> dict[str, float]:
    """p50 / p95 / mean response latency in milliseconds over all attempts."""
    latencies = [r.latency_ms for r in records]
    if not latencies:
        return {"p50_ms": 0.0, "p95_ms": 0.0, "mean_ms": 0.0}
    return {
        "p50_ms": round(percentile(latencies, 0.50), 2),
        "p95_ms": round(percentile(latencies, 0.95), 2),
        "mean_ms": round(sum(latencies) / len(latencies), 2),
    }


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def cost_summary(records: list[PredictionRecord], model: str) -> dict[str, Any]:
    """Estimated USD cost per case and per 1,000 cases, with assumptions."""
    price = price_for(model)
    input_tokens = 0
    output_tokens = 0
    usage_estimated = False
    for record in records:
        if record.input_tokens is None:
            usage_estimated = True  # provider did not report usage
        input_tokens += record.input_tokens or 0
        output_tokens += record.output_tokens or _estimate_tokens(record.raw_content)
    n = len(records)
    total = (
        input_tokens * price.input_per_mtok + output_tokens * price.output_per_mtok
    ) / 1_000_000
    cache_part = ""
    if price.cache_read_per_mtok is not None:
        cache_part = f", cache_read ${price.cache_read_per_mtok}/Mtok"
    return {
        "model": model,
        "provider": price.provider,
        "total_input_tokens": input_tokens,
        "total_output_tokens": output_tokens,
        "tokens_estimated_when_missing": usage_estimated,
        "usd_total": round(total, 6),
        "usd_per_case": round(total / n, 6) if n else 0.0,
        "usd_per_1000_cases": round(total / n * 1000, 4) if n else 0.0,
        "price_basis": (
            f"input ${price.input_per_mtok}/Mtok, "
            f"output ${price.output_per_mtok}/Mtok{cache_part}, "
            f"as of {price.as_of}"
        ),
        "price_note": price.note,
    }
