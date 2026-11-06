"""The benchmark runner: load → validate → infer → score → record.

The runner is deliberately provider-agnostic and synchronous (sequential
inference first: predictable rate limits, reproducible latency, easy
debugging). Concurrency can be added later behind the same contract.
"""

from __future__ import annotations

import hashlib
import json
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
from .config import ExperimentConfig, ProviderSection
from .evidence import default_evidence_fields
from .metrics import compute_metrics
from .notify import post_run_webhook
from .parsing import parse_prediction
from .prompts import resolve_system_prompt
from .providers import build_provider
from .providers.base import ModelProvider, ProviderError
from .registry import DatasetInfo, default_datasets_root, load_dataset, load_split
from .reporting import ensure_dir, render_report, write_json, write_predictions
from .schemas import BenchmarkCase, Category, PredictionRecord
from .tracing import (
    SPAN_PROVIDER_CALL,
    SPAN_SCORE,
    TRACE_FILENAME,
    SpanProxyProvider,
    TraceRecorder,
)


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
    "ollama": "beam:cloud",
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


def provider_substitution(
    config: ExperimentConfig,
    requested: ProviderSection | None = None,
) -> dict[str, dict[str, str]] | None:
    """What the run will use instead of what was asked for, if they differ.

    ``requested`` is for callers that already rewrote ``config.provider``; it
    defaults to the config's own provider section.
    """
    asked = requested or config.provider
    name, model = _resolve_provider_and_model(config)
    if (asked.name, asked.model) == (name, model):
        return None
    return {
        "requested": {"name": asked.name, "model": asked.model},
        "resolved": {"name": name, "model": model},
    }


def _make_provider(
    config: ExperimentConfig,
    examples: list[dict[str, Any]],
    system_text: str | None = None,
) -> ModelProvider:
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
    # ``system_text`` is the resolved prompt: registry body when
    # ``prompt.name`` is set, otherwise the inline ``prompt.system``.
    if system_text:
        options["system_prompt"] = system_text
    if examples:
        options.setdefault("examples", examples)
    return build_provider(provider_name, model=provider_model, options=options)


def _effective_prompt_meta(
    provider: ModelProvider, prompt_meta: dict[str, Any] | None
) -> dict[str, Any]:
    """Record the system prompt a provider will *actually* send.

    A manifest that only says what the config asked for can still lie: the
    provider may have substituted its built-in default (the ``source: none``
    case) or appended instructions of its own. Hashing the text the provider
    holds closes that gap — ``effective_sha256`` is the number to compare
    across runs.
    """
    meta = dict(prompt_meta or {})
    effective = getattr(provider, "system_prompt", None)
    if not isinstance(effective, str) or not effective:
        return meta
    meta["effective_sha256"] = hashlib.sha256(effective.encode("utf-8")).hexdigest()
    if meta.get("source") in (None, "none"):
        meta["source"] = "provider_default"
        meta["chars"] = len(effective)
    elif meta.get("sha256") and meta["sha256"] != meta["effective_sha256"]:
        # The provider altered the text (e.g. appended instructions): keep both
        # digests so the discrepancy is visible rather than silently absorbed.
        meta["effective_differs"] = True
    return meta


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


def environment_info() -> dict[str, Any]:
    """The software a run executed on, for its manifest."""
    return {
        "forgebench_version": __version__,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "git_sha": _git_sha(Path(__file__).resolve().parents[2]),
    }


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


def _evaluate_reason_with_judge(
    judge_section: Any,
    case: BenchmarkCase,
    record: PredictionRecord,
    judge_provider: Any,
) -> tuple[float, bool, str] | None:
    """G-Eval score for one schema-valid prediction's stated reason.

    Returns ``(score, pass, reason)`` or ``None`` when the judge could not
    produce a verdict — a broken judge must never fail the benchmark run.
    """
    from .judge import build_judge_prompt, call_judge

    actual: dict[str, Any] = {"category": record.category.value if record.category else None}
    try:
        parsed = json.loads(record.raw_content)
        if isinstance(parsed, dict):
            actual["reason"] = parsed.get("reason", "")
            actual["requires_review"] = parsed.get("requires_review")
    except (json.JSONDecodeError, TypeError):
        actual["reason"] = ""

    prompt = build_judge_prompt(
        judge_section.criteria or DEFAULT_JUDGE_CRITERIA,
        input_text="\n".join(f"{k}: {v}" for k, v in case.input.items()),
        actual_output=actual,
        expected_output={
            "category": case.expected.category.value,
            "requires_review": case.expected.requires_review,
        },
    )
    try:
        score, verdict, reason, _response = call_judge(judge_provider, prompt)
    except ProviderError:
        return None
    return score, verdict, reason


DEFAULT_JUDGE_CRITERIA = (
    "Assess whether the model's stated reason is factually grounded in the "
    "given input and correctly justifies the predicted category."
)


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


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
    on_log: Callable[[str], None] | None = None,
    requested_provider: ProviderSection | None = None,
) -> RunResult:
    """Execute one experiment end to end and persist all artifacts.

    ``on_log`` receives human-readable milestone lines (config loaded,
    provider ready, per-case results, metrics) so callers such as the
    dashboard can stream an execution log while the run is in flight.

    ``requested_provider`` names the provider originally asked for when the
    caller already replaced it in ``config``, so the manifest can still record
    the substitution.
    """
    started = time.perf_counter()
    _log = on_log or (lambda _msg: None)
    from .credits import BENCHMARK_RUN_CREDITS, consume_run, run_credit_id

    root = datasets_root or default_datasets_root()

    cases, info = load_dataset(config.experiment.dataset, config.experiment.split, root)
    if config.experiment.dataset_version and info.version != config.experiment.dataset_version:
        raise ValueError(
            f"config pins dataset {config.experiment.dataset}=={config.experiment.dataset_version} "
            f"but the registry has version {info.version}"
        )
    if limit is not None:
        cases = cases[:limit]

    _log(
        f"config {config.experiment.name} · dataset {info.name}@{info.version} "
        f"({config.experiment.split}) · {len(cases)} cases"
    )

    examples: list[dict[str, Any]] = []
    build_started = time.perf_counter()
    if config.prompt.few_shot_count:
        train_cases = load_split(config.experiment.dataset, "train", root)
        examples = build_few_shot_examples(train_cases, config.prompt.few_shot_count)

    system_text, prompt_meta = resolve_system_prompt(
        config.prompt.name, config.prompt.version, config.prompt.system
    )
    provider = _make_provider(config, examples, system_text)
    prompt_build_ms = (time.perf_counter() - build_started) * 1000.0
    prompt_meta = _effective_prompt_meta(provider, prompt_meta)
    _log(f"provider {provider.name} · model {provider.model}")

    substitution = provider_substitution(config, requested_provider)
    if substitution:
        _log(
            f"warning: config asks for {substitution['requested']['name']}; "
            f"running on {substitution['resolved']['name']}"
        )

    # Metering: one benchmark run = one flat price (30 credits = $3.00), charged
    # only once the run can start, so a bad dataset or provider costs nothing.
    consume_run("benchmark", run_credit_id(config.experiment.name), amount=BENCHMARK_RUN_CREDITS)

    # Optional LLM-as-judge on top of the rule-based metrics. Built once; a
    # judge that cannot be constructed disables judging with a loud warning
    # rather than failing the whole experiment.
    judge_section = config.evaluation.judge
    judge_instance: ModelProvider | None = None
    judge_warning: str | None = None
    if judge_section is not None:
        try:
            judge_instance = build_provider(
                judge_section.provider, model=judge_section.model, options=judge_section.options
            )
            _log(
                f"judge {judge_section.provider} · model "
                f"{judge_instance.model or judge_section.model}"
            )
        except Exception as exc:  # noqa: BLE001 - judge is optional
            judge_warning = str(exc)
            _log(f"judge unavailable ({exc}) — judging is advisory")

    recorder = TraceRecorder()
    records: list[PredictionRecord] = []
    judge_scores: list[tuple[float, bool]] = []
    judge_failures = 0
    total = len(cases)
    for index, case in enumerate(cases, start=1):
        case_started = time.perf_counter()
        with recorder.case(case.id) as trace:
            call_started = time.perf_counter()
            record = None
            try:
                response = provider.predict(case)
            except ProviderError as exc:
                trace.add(
                    SPAN_PROVIDER_CALL,
                    (time.perf_counter() - call_started) * 1000.0,
                    error=str(exc),
                    detail={"provider": provider.name, "model": provider.model},
                )
                record = _provider_failure_record(case, exc)
                records.append(record)
            else:
                trace.add(
                    SPAN_PROVIDER_CALL,
                    (time.perf_counter() - call_started) * 1000.0,
                    detail={
                        "provider": provider.name,
                        "model": provider.model,
                        "reported_ms": round(response.latency_ms, 3),
                        "input_tokens": response.input_tokens,
                        "output_tokens": response.output_tokens,
                    },
                )
                score_started = time.perf_counter()
                record = score_case(
                    case,
                    response.content,
                    response.latency_ms,
                    response.input_tokens,
                    response.output_tokens,
                )
                judge_ms = [0.0]
                judge_score: float | None = None
                if judge_instance is not None and record.ok:
                    judge_for_case = SpanProxyProvider(
                        judge_instance,
                        trace,
                        on_ms=lambda ms, acc=judge_ms: acc.__setitem__(0, acc[0] + ms),
                    )
                    try:
                        verdict = _evaluate_reason_with_judge(
                            judge_section,
                            case,
                            record,
                            judge_for_case,
                        )
                    except Exception:  # noqa: BLE001 - judging is advisory
                        verdict = None
                    if verdict is None:
                        judge_failures += 1
                    else:
                        judge_score, passed, _reason = verdict
                        judge_scores.append((judge_score, passed))
                trace.add(
                    SPAN_SCORE,
                    (time.perf_counter() - score_started) * 1000.0 - judge_ms[0],
                    detail={
                        "ok": record.ok,
                        "correct": record.correct,
                        "error_kind": record.error_kind,
                        "judge_score": judge_score,
                        "judge_ms": round(judge_ms[0], 3),
                    },
                )
                records.append(record)
        if on_progress:
            on_progress(index, total)
        case_ms = (time.perf_counter() - case_started) * 1000.0
        if record is not None and record.ok:
            _log(f"[{index}/{total}] ✓ {case.id} · correct={record.correct} · {case_ms:.0f} ms")
        elif record is not None:
            _log(
                f"[{index}/{total}] ✗ {case.id} · error {record.error_kind or 'invalid'} · "
                f"{case_ms:.0f} ms"
            )

    metrics = compute_metrics(records, config.evaluation.metrics, model=provider.model)
    _log(
        "metrics computed: "
        + " · ".join(
            f"{key} {metrics[key]:.4f}"
            for key in ("accuracy", "macro_f1", "schema_validity")
            if key in metrics
        )
    )
    if judge_instance is not None:
        metrics["judge"] = {
            "provider": judge_section.provider,
            "model": judge_instance.model or judge_section.model,
            "n_judged": len(judge_scores),
            "n_failures": judge_failures,
            "avg_score": _mean([s for s, _p in judge_scores]),
            "pass_rate": _mean([1.0 if p else 0.0 for _s, p in judge_scores]),
        }

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
        "environment": environment_info(),
        "few_shot_examples": len(examples),
        "prompt": prompt_meta,
        "prompt_build_ms": round(prompt_build_ms, 3),
        "trace": {"file": TRACE_FILENAME, "n_cases": total},
        "command": " ".join(sys.argv) or None,
    }
    if substitution:
        manifest["provider_substitution"] = substitution
    if judge_instance is not None:
        manifest["judge"] = {
            "name": judge_section.provider,
            "model": judge_instance.model or judge_section.model,
        }
    elif judge_warning:
        manifest["judge"] = {
            "name": judge_section.provider,
            "model": judge_section.model,
            "warning": judge_warning,
        }

    # Per-case test data so the Markdown report can show the inputs alongside
    # the predictions instead of bare case ids.
    case_inputs = {case.id: {"input": case.input} for case in cases}

    write_predictions(records, run_dir / "predictions.jsonl")
    write_json(metrics, run_dir / "metrics.json")
    write_json(manifest, run_dir / "manifest.json")
    recorder.write(run_dir)
    (run_dir / "report.md").write_text(
        render_report(manifest, metrics, records, case_inputs=case_inputs), encoding="utf-8"
    )

    post_run_webhook(manifest, metrics)

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
    "provider_substitution",
    "environment_info",
    "score_case",
    "build_few_shot_examples",
    "Category",
    "DatasetInfo",
]
