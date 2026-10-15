"""Metric unit tests with hand-computed expectations."""

from __future__ import annotations

import pytest

from forgebench.metrics import available_metrics, compute_metrics
from forgebench.metrics.classification import (
    accuracy,
    critical_false_match_rate,
    escalation_recall,
    family_breakdown,
    macro_f1,
    per_class_stats,
)
from forgebench.metrics.performance import percentile
from forgebench.metrics.reliability import error_breakdown, schema_validity
from forgebench.schemas import Category

from .conftest import make_record


def test_perfect_predictions_score_perfectly() -> None:
    records = [
        make_record(Category.MATCHED, Category.MATCHED),
        make_record(Category.AMOUNT_MISMATCH, Category.AMOUNT_MISMATCH),
    ]
    assert accuracy(records) == 1.0
    assert macro_f1(records) == 1.0
    assert critical_false_match_rate(records) == 0.0
    assert escalation_recall(records) == 1.0
    assert schema_validity(records) == 1.0


def test_hand_computed_confusion() -> None:
    # expected matched: one right, one wrong (called amount_mismatch)
    # expected amount: one right, one wrong (called matched -> the dangerous error)
    records = [
        make_record(Category.MATCHED, Category.MATCHED),
        make_record(Category.MATCHED, Category.AMOUNT_MISMATCH),
        make_record(Category.AMOUNT_MISMATCH, Category.AMOUNT_MISMATCH),
        make_record(Category.AMOUNT_MISMATCH, Category.MATCHED),
    ]
    assert accuracy(records) == 0.5
    # matched: tp=1 fp=1 fn=1 -> f1=0.5; amount: tp=1 fp=1 fn=1 -> f1=0.5
    assert macro_f1(records) == pytest.approx(0.5)
    # 1 of 2 truly non-matching cases wrongly called matched
    assert critical_false_match_rate(records) == 0.5
    # 1 of 2 review-worthy cases escalated
    assert escalation_recall(records) == 0.5


def test_invalid_records_are_excluded_from_classification_but_counted() -> None:
    records = [
        make_record(Category.MATCHED, Category.MATCHED),
        make_record(Category.AMOUNT_MISMATCH, None, ok=False, error_kind="malformed_json"),
    ]
    assert accuracy(records) == 1.0  # over schema-valid only
    assert schema_validity(records) == 0.5
    assert error_breakdown(records) == {"malformed_json": 1}


def test_macro_f1_ignores_classes_without_support() -> None:
    records = [
        make_record(Category.MATCHED, Category.MATCHED),
        make_record(Category.MATCHED, Category.MATCHED),
    ]
    stats = per_class_stats(records)
    assert set(stats) == {"matched"}  # empty classes never inflate the mean
    assert macro_f1(records) == 1.0


def test_critical_false_match_rate_denominator_is_truly_non_matching() -> None:
    records = [
        make_record(Category.MATCHED, Category.MATCHED),  # correct; not in denominator
        make_record(Category.MATCHED, Category.AMOUNT_MISMATCH),  # wrong, but not a false match
        make_record(Category.DUPLICATE, Category.MATCHED),  # false match
        make_record(Category.DATE_MISMATCH, Category.DATE_MISMATCH),
    ]
    # denominator: the two non-matching cases; numerator: the one called matched
    assert critical_false_match_rate(records) == 0.5


def test_family_breakdown() -> None:
    records = [
        make_record(Category.MATCHED, Category.MATCHED, family="matched"),
        make_record(Category.AMBIGUOUS, Category.MATCHED, family="ambiguous"),
    ]
    breakdown = family_breakdown(records)
    assert breakdown["matched"]["accuracy"] == 1.0
    assert breakdown["ambiguous"]["accuracy"] == 0.0
    assert breakdown["ambiguous"]["n"] == 1


def test_percentile_interpolates() -> None:
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert percentile(values, 0.5) == 30.0
    assert percentile(values, 0.95) == pytest.approx(48.0)
    assert percentile([], 0.95) == 0.0
    assert percentile([7.0], 0.95) == 7.0


def test_unknown_metric_name_fails_fast() -> None:
    with pytest.raises(ValueError, match="unknown metric"):
        compute_metrics([], ["accuracy", "vibes"], model="rule-mock-v1")
    assert "macro_f1" in available_metrics()


def test_empty_run_is_defined_not_crashing() -> None:
    metrics = compute_metrics([], ["accuracy", "macro_f1", "schema_validity"], model="rule-mock-v1")
    assert metrics["n_cases"] == 0
    assert metrics["accuracy"] == 0.0
    assert metrics["schema_validity"] == 0.0
