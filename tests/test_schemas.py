"""Schema contract tests: what a valid case and a valid prediction are."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from forgebench.schemas import BenchmarkCase, Category, Prediction

from .conftest import make_case


def test_valid_case_roundtrips() -> None:
    case = make_case("FIN-0001", Category.MATCHED)
    restored = BenchmarkCase.model_validate_json(case.model_dump_json())
    assert restored.id == "FIN-0001"
    assert restored.expected.category is Category.MATCHED
    assert restored.expected.requires_review is False


def test_case_id_format_is_enforced() -> None:
    case = make_case("FIN-0001", Category.MATCHED).model_dump()
    case["id"] = "CASE-1"
    with pytest.raises(ValidationError):
        BenchmarkCase.model_validate(case)


def test_case_requires_all_input_fields() -> None:
    case = make_case("FIN-0001", Category.MATCHED).model_dump()
    del case["input"]["ledger_amount"]
    with pytest.raises(ValidationError, match="ledger_amount"):
        BenchmarkCase.model_validate(case)


def test_unknown_category_is_rejected() -> None:
    case = make_case("FIN-0001", Category.MATCHED).model_dump()
    case["expected"]["category"] = "banana"
    with pytest.raises(ValidationError):
        BenchmarkCase.model_validate(case)


def test_prediction_contract() -> None:
    prediction = Prediction.model_validate(
        {
            "category": "amount_mismatch",
            "requires_review": True,
            "reason": "Amounts differ.",
            "evidence_fields": ["bank_amount", "ledger_amount"],
        }
    )
    assert prediction.category is Category.AMOUNT_MISMATCH


def test_prediction_rejects_unknown_fields_and_empty_reason() -> None:
    base = {
        "category": "matched",
        "requires_review": False,
        "reason": "ok",
        "evidence_fields": ["bank_amount"],
    }
    with_extra = {**base, "confidence": 0.99}
    with pytest.raises(ValidationError):
        Prediction.model_validate(with_extra)
    with pytest.raises(ValidationError):
        Prediction.model_validate({**base, "reason": ""})
    with pytest.raises(ValidationError):
        Prediction.model_validate({**base, "evidence_fields": []})
