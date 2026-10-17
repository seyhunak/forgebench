"""Shared fixtures: a tiny six-case dataset (one case per category)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forgebench.config import (
    EvaluationSection,
    ExperimentConfig,
    ExperimentSection,
    ProviderSection,
)
from forgebench.schemas import BenchmarkCase, Category, PredictionRecord

CATEGORIES = list(Category)


def make_case(case_id: str, category: Category) -> BenchmarkCase:
    """One representative input per category, exercising every rule branch."""
    input_fields = {
        "vendor": "Test Vendor",
        "description": "Invoice payment - Test Vendor",
        "bank_amount": "100.00",
        "ledger_amount": "100.00",
        "bank_reference": "INV-1000",
        "ledger_reference": "INV-1000",
        "bank_date": "2026-09-15",
        "ledger_date": "2026-09-15",
    }
    if category is Category.AMOUNT_MISMATCH:
        input_fields["bank_amount"] = "200.00"
    elif category is Category.DATE_MISMATCH:
        input_fields["bank_date"] = "2026-09-16"
    elif category is Category.REFERENCE_MISMATCH:
        input_fields["bank_reference"] = "INV-1001"
    elif category is Category.DUPLICATE:
        input_fields["bank_occurrences"] = "2"
        input_fields["ledger_occurrences"] = "1"
    elif category is Category.AMBIGUOUS:
        input_fields["bank_reference"] = "INV-1008"
        input_fields["bank_date"] = "2026-09-16"
    return BenchmarkCase.model_validate(
        {
            "id": case_id,
            "task": "exception_classification",
            "input": input_fields,
            "expected": {
                "category": category.value,
                "requires_review": category is not Category.MATCHED,
            },
            "scenario_family": category.value,
            "reference_explanation": f"Reference explanation for {category.value}.",
        }
    )


@pytest.fixture()
def tiny_dataset(tmp_path: Path) -> Path:
    """A valid dataset directory with one train and one test case per category."""
    root = tmp_path / "datasets"
    dataset_dir = root / "tiny_v1"
    dataset_dir.mkdir(parents=True)
    for split, offset in (("train", 0), ("test", 100)):
        lines = [
            make_case(f"FIN-{offset + index:04d}", category).model_dump_json()
            for index, category in enumerate(CATEGORIES)
        ]
        (dataset_dir / f"{split}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (dataset_dir / "dataset.json").write_text(
        json.dumps(
            {
                "name": "tiny_v1",
                "version": "1.0.0",
                "task": "exception_classification",
                "families": [c.value for c in CATEGORIES],
                "splits": {"train": {"file": "train.jsonl"}, "test": {"file": "test.jsonl"}},
            }
        ),
        encoding="utf-8",
    )
    (dataset_dir / "dataset_card.md").write_text("# tiny_v1\n", encoding="utf-8")
    return root


_PROVIDER_DEFAULT_MODELS = {
    "openrouter": "openai/gpt-4o-mini",
    "mistral": "ministral-8b-2512",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-5",
    "google": "gemini-flash-latest",
    "ollama": "llama3.1:8b",
}


@pytest.fixture()
def selected_provider() -> str:
    """Provider selected for this test run (environment or OpenRouter default)."""
    import os

    return os.environ.get("FORGEBENCH_TEST_PROVIDER", "openrouter")


@pytest.fixture()
def mock_provider(selected_provider: str) -> str:
    """Alias retained for older tests; defers to the selected provider."""
    return selected_provider


@pytest.fixture()
def mock_config(selected_provider: str) -> ExperimentConfig:
    return ExperimentConfig(
        experiment=ExperimentSection(name="unit", dataset="tiny_v1", dataset_version="1.0.0"),
        provider=ProviderSection(
            name=selected_provider,
            model=_PROVIDER_DEFAULT_MODELS.get(selected_provider, "openai/gpt-4o-mini"),
        ),
        evaluation=EvaluationSection(metrics=["accuracy", "macro_f1", "schema_validity"]),
    )


@pytest.fixture()
def deterministic_provider(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Inject an offline, deterministic provider at the runner's seam.

    Runs never use the mock provider — it was removed from every runtime path —
    so tests that exercise the *pipeline* (artifacts, manifest, trace, compare)
    substitute a fake that answers every case correctly. That keeps the suite
    offline, deterministic, and free of API credits; the live path is covered
    separately by the smoke test that needs a real key.
    """
    import json
    from types import SimpleNamespace

    calls = {"n": 0}

    class FakeProvider:
        """A perfect, silent model: correct JSON every time, constant timing."""

        name = "fake"
        model = "fake-1"

        def __init__(self, system_prompt: str | None = None) -> None:
            self.system_prompt = system_prompt or "deterministic test prompt"

        def predict(self, case):
            calls["n"] += 1
            content = json.dumps(
                {
                    "category": case.expected.category.value,
                    "requires_review": case.expected.requires_review,
                    "reason": "deterministic fake",
                    # Evidence must name at least one field present in the case.
                    "evidence_fields": [next(iter(case.input))],
                }
            )
            return SimpleNamespace(
                content=content,
                latency_ms=5.0,
                input_tokens=12,
                output_tokens=8,
            )

    def _make(config, examples, system_text=None):  # noqa: ANN001 - runner-internal shapes
        return FakeProvider(system_text)

    monkeypatch.setattr("forgebench.runner._make_provider", _make)
    return calls


def make_record(
    expected: Category,
    predicted: Category | None,
    *,
    ok: bool = True,
    error_kind: str | None = None,
    family: str | None = None,
    latency_ms: float = 10.0,
) -> PredictionRecord:
    """Build a scored record directly, for metric unit tests."""
    return PredictionRecord(
        case_id="FIN-0001",
        scenario_family=family or expected.value,
        ok=ok,
        category=predicted,
        requires_review=(predicted is not None and predicted is not Category.MATCHED)
        if ok
        else None,
        expected_category=expected,
        expected_requires_review=expected is not Category.MATCHED,
        correct=(predicted == expected) if ok else None,
        raw_content="{}",
        error_kind=error_kind,
        latency_ms=latency_ms,
    )
