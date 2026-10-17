"""Runner tests: the full pipeline, artifact trail, and failure handling."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from forgebench.config import (
    EvaluationSection,
    ExperimentConfig,
    ExperimentSection,
    PromptSection,
    ProviderSection,
)
from forgebench.providers.base import ProviderError
from forgebench.registry import load_dataset, load_split
from forgebench.runner import build_few_shot_examples, run_experiment, score_case
from forgebench.schemas import BenchmarkCase, Category, ProviderResponse

from .conftest import make_case


def test_full_run_writes_every_artifact(
    tiny_dataset: Path,
    mock_config: ExperimentConfig,
    tmp_path: Path,
    deterministic_provider: dict[str, int],
) -> None:
    result = run_experiment(
        mock_config, datasets_root=tiny_dataset, output_root=tmp_path, run_id="unit-run"
    )
    files = {p.name for p in result.run_dir.iterdir()}
    assert files == {
        "predictions.jsonl",
        "metrics.json",
        "manifest.json",
        "report.md",
        "trace.jsonl",
    }
    assert result.metrics["n_cases"] == 6
    assert result.metrics["n_valid"] == 6
    # The injected provider answers every case correctly.
    assert deterministic_provider["n"] == 6
    assert result.metrics["accuracy"] == 1.0
    assert result.metrics["per_class"]["ambiguous"]["f1"] == 1.0

    manifest = json.loads((result.run_dir / "manifest.json").read_text())
    assert manifest["dataset"]["version"] == "1.0.0"
    assert manifest["dataset"]["split_sha256"]
    # No run ever resolves to the mock provider: the config's provider is
    # honoured, and whatever actually answered is recorded separately.
    assert manifest["config"]["provider"]["name"] == "openrouter"
    assert manifest["provider"]["name"] == "fake"
    assert manifest["prompt"]["source"] == "provider_default"
    assert len(manifest["prompt"]["effective_sha256"]) == 64
    assert manifest["trace"] == {"file": "trace.jsonl", "n_cases": 6}
    report = (result.run_dir / "report.md").read_text()
    assert "Limitations" in report and "unit-run" in report

    predictions = [
        json.loads(line)
        for line in (result.run_dir / "predictions.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert len(predictions) == 6


def test_run_is_reproducible(
    tiny_dataset: Path,
    mock_config: ExperimentConfig,
    tmp_path: Path,
    deterministic_provider: dict[str, int],
) -> None:
    first = run_experiment(
        mock_config, datasets_root=tiny_dataset, output_root=tmp_path, run_id="a"
    )
    second = run_experiment(
        mock_config, datasets_root=tiny_dataset, output_root=tmp_path, run_id="b"
    )
    first_predictions = (first.run_dir / "predictions.jsonl").read_text()
    second_predictions = (second.run_dir / "predictions.jsonl").read_text()
    assert first_predictions == second_predictions
    assert first.metrics == second.metrics


def test_limit_evaluates_first_n_cases(
    tiny_dataset: Path,
    mock_config: ExperimentConfig,
    tmp_path: Path,
    deterministic_provider: dict[str, int],
) -> None:
    result = run_experiment(mock_config, datasets_root=tiny_dataset, output_root=tmp_path, limit=2)
    assert result.metrics["n_cases"] == 2
    assert deterministic_provider["n"] == 2


def test_dataset_version_mismatch_fails_loudly(
    tiny_dataset: Path, mock_config: ExperimentConfig, tmp_path: Path
) -> None:
    mock_config.experiment.dataset_version = "9.9.9"
    with pytest.raises(ValueError, match="pins dataset"):
        run_experiment(mock_config, datasets_root=tiny_dataset, output_root=tmp_path)


def test_provider_failures_are_recorded_not_raised(
    tiny_dataset: Path,
    mock_config: ExperimentConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ExplodingProvider:
        name = "mock"
        model = "rule-mock-v1"

        def predict(self, case: BenchmarkCase) -> ProviderResponse:
            raise ProviderError("network unreachable")

    monkeypatch.setattr("forgebench.runner.build_provider", lambda *a, **k: ExplodingProvider())
    result = run_experiment(mock_config, datasets_root=tiny_dataset, output_root=tmp_path)
    assert result.metrics["n_valid"] == 0
    assert result.metrics["provider_error_rate"] == 1.0
    assert result.metrics["error_breakdown"] == {"provider_error": 6}
    assert all(record.error_kind == "provider_error" for record in result.records)


def test_score_case_outcomes() -> None:
    case = make_case("FIN-0001", Category.AMOUNT_MISMATCH)
    good = json.dumps(
        {
            "category": "amount_mismatch",
            "requires_review": True,
            "reason": "Amounts differ.",
            "evidence_fields": ["bank_amount", "ledger_amount"],
        }
    )
    record = score_case(case, good, 12.0, 100, 50)
    assert record.ok and record.correct is True

    wrong = json.dumps(
        {
            "category": "matched",
            "requires_review": False,
            "reason": "They look fine.",
            "evidence_fields": ["bank_amount"],
        }
    )
    record = score_case(case, wrong, 12.0, None, None)
    assert record.ok and record.correct is False

    broken = score_case(case, "not json at all", 12.0, None, None)
    assert broken.ok is False and broken.error_kind == "malformed_json"


def test_few_shot_examples_come_from_gold_labels() -> None:
    train_cases = load_split("finance_v1", "train")
    examples = build_few_shot_examples(train_cases, 3)
    assert len(examples) == 3
    for example in examples:
        assert set(example) == {"input", "prediction"}
        assert example["prediction"]["category"] in {c.value for c in Category}
        assert example["prediction"]["reason"]


def test_few_shot_count_is_recorded_in_manifest(
    tiny_dataset: Path,
    mock_config: ExperimentConfig,
    tmp_path: Path,
    deterministic_provider: dict[str, int],
) -> None:
    mock_config.experiment.dataset = "tiny_v1"
    mock_config.prompt = PromptSection(few_shot_count=2)
    result = run_experiment(mock_config, datasets_root=tiny_dataset, output_root=tmp_path)
    assert result.manifest["few_shot_examples"] == 2


@pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="live smoke test needs OPENROUTER_API_KEY",
)
def test_live_run_produces_a_real_trace(tmp_path: Path) -> None:
    """One real case through the selected provider: the live path stays wired.

    Everything else in this file runs offline against an injected fake. This
    single test proves the real adapter, retries, and token accounting still
    work end to end — skipped (not failed) when no key is available.
    """
    from forgebench.tracing import TRACE_FILENAME, read_traces

    config = ExperimentConfig(
        experiment=ExperimentSection(name="live-smoke", dataset="finance_v1", split="test"),
        provider=ProviderSection(name="openrouter", model="openai/gpt-4o-mini"),
        evaluation=EvaluationSection(metrics=["accuracy", "schema_validity"]),
    )
    result = run_experiment(config, output_root=tmp_path, limit=1, run_id="live-smoke")

    assert result.metrics["n_cases"] == 1
    assert (result.run_dir / "predictions.jsonl").is_file()
    (trace,) = read_traces(result.run_dir)
    assert {span["name"] for span in trace["spans"]} >= {"provider_call", "score"}
    assert trace["total_ms"] > 0
    assert (result.run_dir / TRACE_FILENAME).is_file()


def test_load_dataset_exposes_hashes(tiny_dataset: Path) -> None:
    cases, info = load_dataset("tiny_v1", "test", tiny_dataset)
    assert len(cases) == 6
    assert info.version == "1.0.0"
    assert len(info.split_hashes["test"]) == 64
