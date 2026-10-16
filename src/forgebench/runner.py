"""The benchmark runner: load → validate → infer → score → record.

The runner is deliberately provider-agnostic and synchronous (sequential
inference first: predictable rate limits, reproducible latency, easy
debugging). Concurrency can be added later behind the same contract.
"""

from __future__ import annotations

import platform
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__
from .config import ExperimentConfig
from .evidence import default_evidence_fields
from .metrics import compute_metrics
from .parsing import parse_prediction
from .providers import build_provider
from .providers.base import ModelProvider, ProviderError
from .registry import DatasetInfo, default_datasets_root, load_dataset, load_split
from .reporting import ensure_dir, render_report, write_json, write_predictions
from .schemas import BenchmarkCase, Category, PredictionRecord


@dataclass
class RunResult:
    run_dir: Path
    run_id: str
    records: list[PredictionRecord]
    metrics: dict[str, Any]
    manifest: dict[str, Any]


def build_few_shot_examples(train_cases: list[BenchmarkCase], count: int) -> list[dict[str, Any]]:
    """Gold examples from the *train* split only, for few-shot prompt variants.

    Using train-split labels here is the whole point: the test split must
    never leak into a prompt.
    """
    examples: list[dict[str, Any]] = []
    for case in train_cases[:count]:
        category = case.expected.category
        reason = getattr(case, "reference_explanation", None) or "Reference label from the dataset."
        examples.append(
            {
                "input": case.input,
                "prediction": {
                    "category": category.value,
                    "requires_review": case.expected.requires_review,
                    "reason": reason,
                    "evidence_fields": default_evidence_fields(category),
                },
            }
        )
    return examples


_DEFAULT_MODELS_FOR_PROVIDER = {
    "openrouter": "openai/gpt-4o-mini",
    "mistral": "ministral-8b-2512",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-5",
    "google": "gemini-flash-latest",
    "ollama": "llama3.1:8b",
}


def _resolve_provider_and_model(config: ExperimentConfig) -> tuple[str, str]:
    """Never run on the mock provider: upgrade it to the selected provider."""
    from .credentials import get_value
    from .providers import PROVIDER_ENV_VARS

    name = config.provider.name
    model = config.provider.model
    if name == "mock":
        resolved = None
        for pid in _DEFAULT_MODELS_FOR_PROVIDER:
            if get_value(PROVIDER_ENV_VARS.get(pid, "")):
                resolved = pid
                break
        name = resolved or "openrouter"
    if name == "mock":
        name = "openrouter"
    if not model or model == "rule-mock-v1":
        env_var = PROVIDER_ENV_VARS.get(name, "")
        if env_var:
            model = (get_value(env_var.replace("_API_KEY", "_MODEL")) or "").strip()
        if not model:
            model = _DEFAULT_MODELS_FOR_PROVIDER.get(name, "openai/gpt-4o-mini")
    return name, model


def _make_provider(config: ExperimentConfig, examples: list[dict[str, Any]]) -> ModelProvider:
    provider_name, provider_model = _resolve_provider_and_model(config)
    options = dict(config.provider.options)
    # Mock-specific options must not leak into real providers.
    MOCK_ONLY = {"defect_rate", "invalid_rate"}
    for key in MOCK_ONLY:
        options.pop(key, None)
    # Common inference settings apply to every real provider.
    options.setdefault("temperature", config.inference.temperature)
    options.setdefault("max_retries", config.inference.max_retries)
    options.setdefault("timeout_seconds", config.inference.timeout_seconds)
    options.setdefault("max_tokens", config.inference.max_tokens)
    if config.prompt.system:
        options.setdefault("system_prompt", config.prompt.system)
    if examples:
        options.setdefault("examples", examples)
    return build_provider(provider_name, model=provider_model, options=options)


def _git_sha(cwd: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() or None if completed.returncode == 0 else None


def score_case(
    case: BenchmarkCase,
    response_content: str,
    latency_ms: float,
    input_tokens: int | None,
    output_tokens: int | None,
) -> PredictionRecord:
    """Validate one raw response against the case and score it."""
    prediction, error_kind, error = parse_prediction(response_content, case)
    if prediction is None:
        return PredictionRecord(
            case_id=case.id,
            scenario_family=case.scenario_family,
            ok=False,
            category=None,
            requires_review=None,
            expected_category=case.expected.category,
            expected_requires_review=case.expected.requires_review,
            correct=None,
            raw_content=response_content,
            error_kind=error_kind,
            error=error,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    return PredictionRecord(
        case_id=case.id,
        scenario_family=case.scenario_family,
        ok=True,
        category=prediction.category,
        requires_review=prediction.requires_review,
        expected_category=case.expected.category,
        expected_requires_review=case.expected.requires_review,
        correct=prediction.category == case.expected.category,
        raw_content=response_content,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _provider_failure_record(case: BenchmarkCase, exc: Exception) -> PredictionRecord:
    return PredictionRecord(
        case_id=case.id,
        scenario_family=case.scenario_family,
        ok=False,
        category=None,
        requires_review=None,
        expected_category=case.expected.category,
        expected_requires_review=case.expected.requires_review,
        correct=None,
        raw_content="",
        error_kind="provider_error",
        error=str(exc),
        latency_ms=0.0,
    )


def run_experiment(
    config: ExperimentConfig,
    *,
    datasets_root: Path | None = None,
    output_root: Path | None = None,
    limit: int | None = None,
    run_id: str | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> RunResult:
    """Execute one experiment end to end and persist all artifacts."""
    started = time.perf_counter()
    root = datasets_root or default_datasets_root()

    cases, info = load_dataset(config.experiment.dataset, config.experiment.split, root)
    if config.experiment.dataset_version and info.version != config.experiment.dataset_version:
        raise ValueError(
            f"config pins dataset {config.experiment.dataset}=={config.experiment.dataset_version} "
            f"but the registry has version {info.version}"
        )
    if limit is not None:
        cases = cases[:limit]

    examples: list[dict[str, Any]] = []
    if config.prompt.few_shot_count:
        train_cases = load_split(config.experiment.dataset, "train", root)
        examples = build_few_shot_examples(train_cases, config.prompt.few_shot_count)

    provider = _make_provider(config, examples)

    records: list[PredictionRecord] = []
    total = len(cases)
    for index, case in enumerate(cases, start=1):
        try:
            response = provider.predict(case)
        except ProviderError as exc:
            records.append(_provider_failure_record(case, exc))
        else:
            records.append(
                score_case(
                    case,
                    response.content,
                    response.latency_ms,
                    response.input_tokens,
                    response.output_tokens,
                )
            )
        if on_progress:
            on_progress(index, total)

    metrics = compute_metrics(records, config.evaluation.metrics, model=provider.model)

    created_at = datetime.now(UTC)
    effective_run_id = run_id or (
        f"{config.experiment.name}-{provider.name}-{created_at.strftime('%Y%m%dT%H%M%SZ')}"
    )
    run_dir = ensure_dir((output_root or Path("runs")) / effective_run_id)

    manifest: dict[str, Any] = {
        "run_id": effective_run_id,
        "experiment_name": config.experiment.name,
        "created_at_utc": created_at.isoformat(timespec="seconds"),
        "duration_seconds": round(time.perf_counter() - started, 3),
        "provider": {"name": provider.name, "model": provider.model},
        "dataset": {
            "name": info.name,
            "version": info.version,
            "split": config.experiment.split,
            "split_sha256": info.split_hashes.get(config.experiment.split),
            "n_cases": total,
        },
        "config": config.model_dump(),
        "environment": {
            "forgebench_version": __version__,
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "git_sha": _git_sha(Path(__file__).resolve().parents[2]),
        },
        "few_shot_examples": len(examples),
        "command": " ".join(sys.argv) or None,
    }

    write_predictions(records, run_dir / "predictions.jsonl")
    write_json(metrics, run_dir / "metrics.json")
    write_json(manifest, run_dir / "manifest.json")
    (run_dir / "report.md").write_text(render_report(manifest, metrics, records), encoding="utf-8")

    return RunResult(
        run_dir=run_dir,
        run_id=effective_run_id,
        records=records,
        metrics=metrics,
        manifest=manifest,
    )


__all__ = [
    "RunResult",
    "run_experiment",
    "score_case",
    "build_few_shot_examples",
    "Category",
    "DatasetInfo",
]
