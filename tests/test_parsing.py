"""Parsing tests: the messy reality of LLM JSON, handled deterministically."""

from __future__ import annotations

from forgebench.parsing import (
    ERROR_EMPTY,
    ERROR_MALFORMED_JSON,
    ERROR_UNKNOWN_CATEGORY,
    ERROR_UNKNOWN_EVIDENCE_FIELD,
    extract_json_text,
    parse_prediction,
)
from forgebench.schemas import Category

from .conftest import make_case

VALID = (
    '{"category": "matched", "requires_review": false, '
    '"reason": "All fields agree.", "evidence_fields": ["bank_amount"]}'
)


def test_plain_json_parses() -> None:
    case = make_case("FIN-0001", Category.MATCHED)
    prediction, kind, _ = parse_prediction(VALID, case)
    assert prediction is not None and kind is None
    assert prediction.category is Category.MATCHED


def test_fenced_and_prose_wrapped_json_parse() -> None:
    case = make_case("FIN-0001", Category.MATCHED)
    fenced = f"Here is my analysis:\n```json\n{VALID}\n```\nDone."
    prediction, kind, _ = parse_prediction(fenced, case)
    assert prediction is not None and kind is None
    inline = f"I think it matches. {VALID} Hope that helps!"
    prediction, kind, _ = parse_prediction(inline, case)
    assert prediction is not None and kind is None


def test_malformed_json_is_flagged() -> None:
    case = make_case("FIN-0001", Category.MATCHED)
    prediction, kind, message = parse_prediction('{"category": "matched", "reason":', case)
    assert prediction is None
    assert kind == ERROR_MALFORMED_JSON
    assert message


def test_empty_response_is_flagged() -> None:
    case = make_case("FIN-0001", Category.MATCHED)
    prediction, kind, _ = parse_prediction("   ", case)
    assert prediction is None and kind == ERROR_EMPTY


def test_unknown_category_is_distinguished_from_general_schema_errors() -> None:
    case = make_case("FIN-0001", Category.MATCHED)
    payload = (
        '{"category": "definitely_wrong", "requires_review": true, '
        '"reason": "x", "evidence_fields": ["bank_amount"]}'
    )
    prediction, kind, _ = parse_prediction(payload, case)
    assert prediction is None and kind == ERROR_UNKNOWN_CATEGORY


def test_evidence_fields_must_exist_in_case_input() -> None:
    case = make_case("FIN-0001", Category.MATCHED)
    payload = (
        '{"category": "matched", "requires_review": false, "reason": "x", '
        '"evidence_fields": ["bank_amount", "moon_phase"]}'
    )
    prediction, kind, message = parse_prediction(payload, case)
    assert prediction is None
    assert kind == ERROR_UNKNOWN_EVIDENCE_FIELD
    assert "moon_phase" in message


def test_extract_json_text_edge_cases() -> None:
    assert extract_json_text("") is None
    assert extract_json_text("no json here") is None
    assert extract_json_text(VALID) == VALID
    assert extract_json_text(f"```\n{VALID}\n```") == VALID
