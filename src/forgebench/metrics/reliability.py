"""Reliability metrics: did the model honour the output contract at all?"""

from __future__ import annotations

from collections import Counter

from ..schemas import PredictionRecord


def schema_validity(records: list[PredictionRecord]) -> float:
    """Valid structured outputs / all outputs. The integration-reliability number."""
    if not records:
        return 0.0
    return sum(1 for r in records if r.ok) / len(records)


def error_breakdown(records: list[PredictionRecord]) -> dict[str, int]:
    """Counts of failure kinds: malformed JSON, schema violations, unknown
    categories, evidence fields not in the case, empty responses, provider
    errors. Sorted for stable diffs between runs."""
    kinds = Counter(r.error_kind for r in records if r.error_kind)
    return dict(sorted(kinds.items()))


def provider_error_rate(records: list[PredictionRecord]) -> float:
    """Calls that produced no model output at all (network, quota, auth)."""
    if not records:
        return 0.0
    return sum(1 for r in records if r.error_kind == "provider_error") / len(records)
