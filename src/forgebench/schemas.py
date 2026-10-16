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

    id: str = Field(
        pattern=r"^[A-Z]{2,4}-\d{4}$",
        description="Stable case id, e.g. FIN-0001, HC-0001.",
    )
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


# ---------------------------------------------------------------------------
# Custom task builder schemas
# ---------------------------------------------------------------------------


class TaskOutputField(BaseModel):
    """One field in the model's expected output for a custom task."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        pattern=r"^[a-z_][a-z0-9_]*$",
        description="Output field name, snake_case, e.g. sentiment.",
    )
    type: str = Field(
        pattern=r"^(string|number|boolean|enum|list\[string\])$",
        description="Value type: string, number, boolean, enum, or list[string].",
    )
    enum_values: list[str] | None = Field(
        default=None,
        description="Allowed values when type is 'enum'.",
    )
    description: str = Field(
        default="",
        description="Human-readable description of the field.",
    )


class ScoringRule(BaseModel):
    """How to score one output field of a custom task."""

    model_config = ConfigDict(extra="forbid")

    field: str = Field(description="Output field name this rule applies to.")
    method: str = Field(
        pattern=r"^(exact_match|f1|contains|boolean|llm_judge)$",
        description=("Scoring method: exact_match, f1, contains, boolean, or llm_judge."),
    )
    weight: float = Field(default=1.0, ge=0.0, le=10.0)
    threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Pass threshold for fuzzy methods (contains, llm_judge).",
    )
    criteria: str | None = Field(
        default=None,
        description=(
            "G-Eval-style criterion in plain language for llm_judge scoring. "
            "Example: 'Determine whether the summary is factually correct.'"
        ),
    )
    evaluation_steps: list[str] | None = Field(
        default=None,
        description=(
            "Chain-of-thought evaluation steps for the judge. "
            "Provide criteria OR evaluation_steps, not both."
        ),
    )


class JudgeConfig(BaseModel):
    """Which provider/model judges subjective scoring rules."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(
        default="",
        description=(
            "Judge provider: empty = use the selected prediction provider/model. "
            "Supported: mistral, openai, anthropic, google, openrouter, ollama."
        ),
    )
    model: str = Field(
        default="",
        description="Judge model id. Empty = provider default. "
        "Prefer a cheap model (e.g. gpt-4o-mini) for judging.",
    )


class TaskCase(BaseModel):
    """One test case for a custom task."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(pattern=r"^[A-Z]{2,4}-\d{4}$", description="Stable case id.")
    input: dict[str, Any] = Field(description="Field values visible to the model.")
    expected: dict[str, Any] = Field(description="Ground-truth values matching the output schema.")
    context: list[str] | None = Field(
        default=None,
        description="Ideal ground-truth context (RAG goldens).",
    )
    retrieval_context: list[str] | None = Field(
        default=None,
        description="What the RAG pipeline actually retrieved at runtime.",
    )


class TaskDefinition(BaseModel):
    """User-defined evaluation task. Lives in tasks/<name>/task.yaml."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
        max_length=60,
        description="Task identifier, e.g. sentiment_analysis.",
    )
    version: str = "1.0.0"
    description: str = ""
    input_fields: list[str] = Field(
        min_length=1,
        description="Field names the model receives as input.",
    )
    output_schema: list[TaskOutputField] = Field(
        min_length=1,
        description="Expected output fields and their types.",
    )
    scoring_rules: list[ScoringRule] = Field(
        min_length=1,
        description="How each output field is scored.",
    )
    system_prompt: str | None = Field(
        default=None,
        description="System prompt injected for this task.",
    )
    judge: JudgeConfig = Field(
        default_factory=JudgeConfig,
        description="Provider/model that judges subjective (llm_judge) rules.",
    )
