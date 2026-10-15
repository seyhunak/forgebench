"""Task-quality metrics. Pure Python, deterministic, no LLM-as-judge.

Denominator conventions (also documented in docs/benchmark_protocol.md):

* Classification metrics (accuracy, macro-F1, false-match rate, escalation
  recall) are computed over **schema-valid** predictions only. Invalid output
  is measured separately by ``schema_validity`` so a model cannot look smart
  by failing loudly on hard cases.
* Macro-F1 averages F1 over the categories that appear in the ground truth of
  the evaluated records, so an empty class never inflates the score.
"""

from __future__ import annotations

from collections import Counter

from ..schemas import Category, PredictionRecord


def valid_records(records: list[PredictionRecord]) -> list[PredictionRecord]:
    return [r for r in records if r.ok]


def accuracy(records: list[PredictionRecord]) -> float:
    """Correct classifications / schema-valid classifications."""
    valid = valid_records(records)
    if not valid:
        return 0.0
    return sum(1 for r in valid if r.category == r.expected_category) / len(valid)


def _f1(tp: int, fp: int, fn: int) -> float:
    if tp == 0:
        return 0.0
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    return 2 * precision * recall / (precision + recall)


def per_class_stats(records: list[PredictionRecord]) -> dict[str, dict[str, float | int]]:
    """Support / precision / recall / F1 for every category with ground truth."""
    valid = valid_records(records)
    stats: dict[str, dict[str, float | int]] = {}
    for category in Category:
        support = sum(1 for r in valid if r.expected_category == category)
        if support == 0:
            continue
        tp = sum(1 for r in valid if r.expected_category == category and r.category == category)
        fp = sum(1 for r in valid if r.expected_category is not category and r.category == category)
        fn = support - tp
        stats[category.value] = {
            "support": support,
            "precision": tp / (tp + fp) if tp + fp else 0.0,
            "recall": tp / support,
            "f1": _f1(tp, fp, fn),
        }
    return stats


def macro_f1(records: list[PredictionRecord]) -> float:
    """Unweighted mean of per-class F1 over categories with ground truth."""
    stats = per_class_stats(records)
    if not stats:
        return 0.0
    return sum(entry["f1"] for entry in stats.values()) / len(stats)


def confusion_matrix(records: list[PredictionRecord]) -> dict[str, dict[str, int]]:
    """expected -> predicted -> count, over schema-valid predictions."""
    matrix: dict[str, dict[str, int]] = {}
    for record in valid_records(records):
        expected = record.expected_category.value
        predicted = record.category.value if record.category else "<invalid>"
        matrix.setdefault(expected, {}).setdefault(predicted, 0)
        matrix[expected][predicted] += 1
    return matrix


def critical_false_match_rate(records: list[PredictionRecord]) -> float:
    """Truly non-matching cases wrongly declared ``matched``.

    Denominator: schema-valid predictions whose ground truth is NOT matched.
    This is the financially dangerous error (approving a discrepancy) and is
    deliberately kept separate from ordinary accuracy.
    """
    truly_non_matching = [
        r for r in valid_records(records) if r.expected_category is not Category.MATCHED
    ]
    if not truly_non_matching:
        return 0.0
    false_matches = sum(1 for r in truly_non_matching if r.category is Category.MATCHED)
    return false_matches / len(truly_non_matching)


def escalation_recall(records: list[PredictionRecord]) -> float:
    """Of the cases that require human review, how many were escalated?"""
    requiring = [r for r in valid_records(records) if r.expected_requires_review]
    if not requiring:
        return 0.0
    escalated = sum(1 for r in requiring if r.requires_review is True)
    return escalated / len(requiring)


def family_breakdown(records: list[PredictionRecord]) -> dict[str, dict[str, float | int]]:
    """Per scenario family: size, validity, and accuracy over valid outputs."""
    by_family: dict[str, list[PredictionRecord]] = {}
    for record in records:
        by_family.setdefault(record.scenario_family, []).append(record)
    breakdown: dict[str, dict[str, float | int]] = {}
    for family in sorted(by_family):
        family_records = by_family[family]
        valid = valid_records(family_records)
        correct = sum(1 for r in valid if r.category == r.expected_category)
        breakdown[family] = {
            "n": len(family_records),
            "n_valid": len(valid),
            "accuracy": correct / len(valid) if valid else 0.0,
        }
    return breakdown


def class_distribution(records: list[PredictionRecord]) -> dict[str, int]:
    """Ground-truth class distribution of the evaluated slice."""
    return dict(sorted(Counter(r.expected_category.value for r in records).items()))
