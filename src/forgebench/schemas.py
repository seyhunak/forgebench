"""Pydantic contracts shared across ForgeBench.

Three contracts live here and nothing else should invent its own:

* ``BenchmarkCase``   -- one test case as stored in a dataset JSONL file.
* ``Prediction``      -- the exact JSON shape a model must return.
* ``PredictionRecord``-- one scored case inside a run's predictions file.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Fields every case must expose to the model. Extra fields are allowed and
#: used by specific scenario families (e.g. ``bank_occurrences``).
REQUIRED_INPUT_KEYS = (
    "bank_amount",
    "ledger_amount",
    "bank_reference",
    "ledger_reference",
    "bank_date",
    "ledger_date",
)


class Category(StrEnum):
    """The closed classification schema. Unknown values are rejected."""

    MATCHED = "matched"
    AMOUNT_MISMATCH = "amount_mismatch"
    DATE_MISMATCH = "date_mismatch"
    REFERENCE_MISMATCH = "reference_mismatch"
    DUPLICATE = "duplicate"
    AMBIGUOUS = "ambiguous"


#: Every category other than MATCHED implies the case needs a human.
REVIEW_CATEGORIES = frozenset(c for c in Category if c is not Category.MATCHED)


class Expected(BaseModel):
    """Ground truth for one case."""

    model_config = ConfigDict(extra="forbid")

    category: Category
    requires_review: bool


class BenchmarkCase(BaseModel):
    """One synthetic reconciliation case with deterministic ground truth."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(pattern=r"^FIN-\d{4}$", description="Stable case id, e.g. FIN-0001.")
    task: str = "exception_classification"
    input: dict[str, str] = Field(description="Fields visible to the model, all values strings.")
    expected: Expected
    scenario_family: str = Field(description="matched | amount_mismatch | ... | ambiguous")
    notes: str | None = None

    @model_validator(mode="after")
    def _check_input(self) -> BenchmarkCase:
        if not self.input:
            raise ValueError("case input must not be empty")
        missing = [k for k in REQUIRED_INPUT_KEYS if k not in self.input]
        if missing:
            raise ValueError(f"case {self.id} input is missing required keys: {missing}")
        return self


class Prediction(BaseModel):
    """The output contract every provider must satisfy.

    A model response is only credited as correct if it validates against this
    schema *and* its ``evidence_fields`` exist in the case input.
    """

    model_config = ConfigDict(extra="forbid")

    category: Category
    requires_review: bool
    reason: str = Field(min_length=1, max_length=600)
    evidence_fields: list[str] = Field(min_length=1)


class ProviderResponse(BaseModel):
    """Raw provider output plus the operational facts the metric engine needs."""

    content: str
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    model: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class PredictionRecord(BaseModel):
    """One scored case; the unit of the run's predictions.jsonl."""

    case_id: str
    scenario_family: str
    ok: bool
    category: Category | None
    requires_review: bool | None
    expected_category: Category
    expected_requires_review: bool
    correct: bool | None
    raw_content: str
    error_kind: str | None = None
    error: str | None = None
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
