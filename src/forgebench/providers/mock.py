"""A deterministic, offline stand-in for a real model.

The mock provider exists so contributors can run the full pipeline and the
test suite without an API key or a GPU. It is **not** a language model: it
applies the same deterministic reconciliation rules the dataset generator
documents, then optionally injects two kinds of realistic imperfection:

* ``defect_rate``  -- deterministic misclassifications, to simulate a model
  that is right most of the time but wrong in structured ways.
* ``invalid_rate`` -- deterministic schema violations (malformed JSON,
  missing fields, unknown categories), to exercise the validity metrics.

Both rates are driven by a hash of ``(seed, case_id)``, so the same config
always produces the same predictions, run after run.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Any

from ..schemas import BenchmarkCase, Category, ProviderResponse
from .base import ProviderError

_DEFAULT_SYSTEM_PROMPT = (
    "You are a deterministic rule engine. (Prompt variants only affect real providers.)"
)

#: Wrong-category pool used when a defect is injected. Deterministic per case.
_DEFECT_POOL = (
    Category.AMOUNT_MISMATCH,
    Category.DATE_MISMATCH,
    Category.REFERENCE_MISMATCH,
    Category.DUPLICATE,
    Category.AMBIGUOUS,
    Category.MATCHED,
)

_MALFORMED_SAMPLES = (
    '{"category": "matched", "requires_review": false, "reason": "looks fine',
    "The bank and ledger entries match on all fields.",
    '{"category": "bogus_category", "requires_review": false, "reason": "x", "evidence": []}',
    '{"category": "matched", "requires_review": false, "reason": "missing evidence field"}',
)


def _unit_hash(seed: int, case_id: str, salt: str) -> float:
    """A stable float in [0, 1) derived from the case id. No RNG state anywhere."""
    digest = hashlib.sha256(f"{seed}:{salt}:{case_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


class MockProvider:
    """Rule-based deterministic provider. Implements the ModelProvider contract."""

    name = "mock"

    def __init__(
        self,
        model: str = "rule-mock-v1",
        *,
        defect_rate: float = 0.0,
        invalid_rate: float = 0.0,
        seed: int = 42,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> None:
        if not 0.0 <= defect_rate <= 1.0:
            raise ProviderError("mock defect_rate must be within [0, 1]")
        if not 0.0 <= invalid_rate <= 1.0:
            raise ProviderError("mock invalid_rate must be within [0, 1]")
        self.model = model
        self.defect_rate = defect_rate
        self.invalid_rate = invalid_rate
        self.seed = seed
        # Accepted so mock configs can mirror real experiment configs; ignored.
        self.system_prompt = system_prompt or _DEFAULT_SYSTEM_PROMPT
        self._extra_options = kwargs

    # -- deterministic rules -------------------------------------------------

    @staticmethod
    def _amounts(case: BenchmarkCase) -> tuple[Decimal | None, Decimal | None]:
        try:
            return (
                Decimal(case.input["bank_amount"]),
                Decimal(case.input["ledger_amount"]),
            )
        except (InvalidOperation, KeyError):
            return None, None

    def classify(self, case: BenchmarkCase) -> Category:
        """Classify from visible input fields only. Never reads ``expected``."""
        data = case.input
        bank_occ = data.get("bank_occurrences")
        ledger_occ = data.get("ledger_occurrences")
        if bank_occ is not None and ledger_occ is not None and bank_occ != ledger_occ:
            return Category.DUPLICATE
        bank_amount, ledger_amount = self._amounts(case)
        if bank_amount is not None and ledger_amount is not None and bank_amount != ledger_amount:
            return Category.AMOUNT_MISMATCH
        if data["bank_reference"].strip() != data["ledger_reference"].strip():
            return Category.REFERENCE_MISMATCH
        if data["bank_date"] != data["ledger_date"]:
            return Category.DATE_MISMATCH
        return Category.MATCHED

    # -- contract ------------------------------------------------------------

    def predict(self, case: BenchmarkCase) -> ProviderResponse:
        category = self.category_for(case)

        invalid_roll = _unit_hash(self.seed, case.id, "invalid")
        if invalid_roll < self.invalid_rate:
            sample = _MALFORMED_SAMPLES[
                int(invalid_roll / max(self.invalid_rate, 1e-9)) % len(_MALFORMED_SAMPLES)
            ]
            content = sample
        else:
            payload = {
                "category": category.value,
                "requires_review": category is not Category.MATCHED,
                "reason": self._reason(category),
                "evidence_fields": self._evidence(category),
            }
            content = json.dumps(payload)

        latency_ms = 12.0 + _unit_hash(self.seed, case.id, "latency") * 30.0
        return ProviderResponse(
            content=content,
            latency_ms=latency_ms,
            input_tokens=max(1, len(json.dumps(case.input)) // 4),
            output_tokens=max(1, len(content) // 4),
            model=self.model,
        )

    def category_for(self, case: BenchmarkCase) -> Category:
        """Rule classification plus deterministic defect injection."""
        category = self.classify(case)
        defect_roll = _unit_hash(self.seed, case.id, "defect")
        if defect_roll < self.defect_rate:
            wrong = [c for c in _DEFECT_POOL if c is not category]
            return wrong[int(defect_roll / max(self.defect_rate, 1e-9) * 977) % len(wrong)]
        return category

    @staticmethod
    def _reason(category: Category) -> str:
        return {
            Category.MATCHED: "Bank and ledger fields agree on amount, date and reference.",
            Category.AMOUNT_MISMATCH: "Bank and ledger amounts differ.",
            Category.DATE_MISMATCH: "Bank and ledger dates differ.",
            Category.REFERENCE_MISMATCH: "Bank and ledger references differ.",
            Category.DUPLICATE: "The bank side shows more occurrences than the ledger side.",
            Category.AMBIGUOUS: "Signals conflict; escalate for human review.",
        }[category]

    @staticmethod
    def _evidence(category: Category) -> list[str]:
        return {
            Category.MATCHED: ["bank_amount", "ledger_amount"],
            Category.AMOUNT_MISMATCH: ["bank_amount", "ledger_amount"],
            Category.DATE_MISMATCH: ["bank_date", "ledger_date"],
            Category.REFERENCE_MISMATCH: ["bank_reference", "ledger_reference"],
            Category.DUPLICATE: ["bank_occurrences", "ledger_occurrences"],
            Category.AMBIGUOUS: ["bank_reference", "ledger_reference", "bank_date", "ledger_date"],
        }[category]

    # -- custom task support --------------------------------------------------

    def predict_text(
        self,
        prompt: str,
        output_schema: list[dict] | None = None,
    ) -> ProviderResponse:
        """Generate a deterministic mock response for custom task evaluation.

        Inspects the output schema and produces plausible JSON values for each
        field. Output is deterministic given the prompt text.
        """
        import hashlib as _hashlib

        digest = _hashlib.sha256(prompt.encode()).digest()
        seed_val = int.from_bytes(digest[:4], "big") / 2**32

        result: dict = {}
        if output_schema:
            for field in output_schema:
                fname = field["name"]
                ftype = field["type"]
                enum_values = field.get("enum_values")

                if ftype == "enum" and enum_values:
                    idx = int(seed_val * len(enum_values)) % len(enum_values)
                    result[fname] = enum_values[idx]
                elif ftype == "boolean":
                    result[fname] = seed_val > 0.5
                elif ftype == "number":
                    result[fname] = round(0.5 + seed_val, 2)
                elif ftype == "list[string]":
                    result[fname] = [f"key_phrase_{i}" for i in range(1, 3)]
                else:  # string
                    result[fname] = f"mock_{fname}"

        content = json.dumps(result)
        latency_ms = 12.0 + seed_val * 30.0
        return ProviderResponse(
            content=content,
            latency_ms=latency_ms,
            input_tokens=max(1, len(prompt) // 4),
            output_tokens=max(1, len(content) // 4),
            model=self.model,
        )
