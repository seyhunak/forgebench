"""Default evidence fields per category, used to build few-shot gold outputs."""

from __future__ import annotations

from .schemas import Category

DEFAULT_EVIDENCE: dict[Category, list[str]] = {
    Category.MATCHED: ["bank_amount", "ledger_amount", "bank_date", "ledger_date"],
    Category.AMOUNT_MISMATCH: ["bank_amount", "ledger_amount"],
    Category.DATE_MISMATCH: ["bank_date", "ledger_date"],
    Category.REFERENCE_MISMATCH: ["bank_reference", "ledger_reference"],
    Category.DUPLICATE: ["bank_occurrences", "ledger_occurrences"],
    Category.AMBIGUOUS: ["bank_reference", "ledger_reference", "bank_date", "ledger_date"],
}


def default_evidence_fields(category: Category) -> list[str]:
    return list(DEFAULT_EVIDENCE[category])
