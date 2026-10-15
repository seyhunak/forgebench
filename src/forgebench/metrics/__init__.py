"""Metric registry: config metric names -> computed values."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..schemas import PredictionRecord
from .classification import (
    accuracy,
    critical_false_match_rate,
    escalation_recall,
    family_breakdown,
    macro_f1,
    per_class_stats,
)
from .performance import cost_summary, latency_summary
from .reliability import error_breakdown, provider_error_rate, schema_validity

MetricFn = Callable[[list[PredictionRecord]], Any]

#: Metrics that need no extra context beyond the scored records.
_SIMPLE_METRICS: dict[str, MetricFn] = {
    "accuracy": accuracy,
    "macro_f1": macro_f1,
    "critical_false_match_rate": critical_false_match_rate,
    "escalation_recall": escalation_recall,
    "schema_validity": schema_validity,
    "latency": latency_summary,
}

#: Metrics that depend on the evaluated model or a config choice.
_CONTEXT_METRICS = {"estimated_cost"}


def available_metrics() -> list[str]:
    return sorted([*_SIMPLE_METRICS, *_CONTEXT_METRICS])


def compute_metrics(
    records: list[PredictionRecord],
    names: list[str],
    *,
    model: str,
) -> dict[str, Any]:
    """Compute the requested metrics plus fixed context (counts, per-class detail).

    Unknown metric names raise, so a typo in an experiment config fails fast
    instead of silently producing an incomplete report.
    """
    unknown = sorted(set(names) - set(available_metrics()))
    if unknown:
        raise ValueError(f"unknown metric(s) {unknown}; available: {available_metrics()}")

    results: dict[str, Any] = {
        "n_cases": len(records),
        "n_valid": sum(1 for r in records if r.ok),
    }
    for name in names:
        if name == "estimated_cost":
            results[name] = cost_summary(records, model)
        else:
            results[name] = _SIMPLE_METRICS[name](records)

    # Always recorded, cheap, and indispensable for honest error analysis.
    results["per_class"] = per_class_stats(records)
    results["family_breakdown"] = family_breakdown(records)
    results["error_breakdown"] = error_breakdown(records)
    results["provider_error_rate"] = provider_error_rate(records)
    return results
