"""Reusable task-execution engine shared by the CLI and the API.

Both ``forgebench task-run`` (CLI) and ``POST /api/tasks/{name}/run`` (HTTP)
drive the same loop so results are identical regardless of entry point.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .cli import _build_task_prompt, _score_task_output
from .providers import build_provider, task_provider_options
from .schemas import (
    Category,
    JudgeConfig,
    PredictionRecord,
)
from .tasks import load_task_with_cases
from .tracing import (
    SPAN_PROVIDER_CALL,
    SPAN_SCORE,
    TRACE_FILENAME,
    SpanProxyProvider,
    TraceRecorder,
)


@dataclass
class TaskRunResult:
    run_id: str
    run_dir: Path
    n_cases: int
    n_valid: int
    metrics: dict[str, Any]
    manifest: dict[str, Any]


def run_task_experiment(
    name: str,
    split: str = "test",
    provider: str = "",
    model: str = "",
    judge_provider: str = "",
    judge_model: str = "",
    limit: int | None = None,
    tasks_root: Path | None = None,
    output_root: Path | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> TaskRunResult:
    """Execute one custom-task evaluation end-to-end."""
    if not provider:
        from .credentials import get_value
        from .providers import PROVIDER_ENV_VARS

        resolved = None
        for pid in ("openrouter", "mistral", "openai", "anthropic", "google", "ollama"):
            if get_value(PROVIDER_ENV_VARS.get(pid, "")):
                resolved = pid
                break
        provider = resolved or provider or "openrouter"
    if not model:
        from .credentials import get_value
        from .providers import PROVIDER_ENV_VARS

        env_var = PROVIDER_ENV_VARS.get(provider, "")
        if env_var:
            model = (get_value(env_var.replace("_API_KEY", "_MODEL")) or "").strip()
    try:
        task, cases = load_task_with_cases(name, split, tasks_root)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"task '{name}' not found: {exc}") from exc

    if limit is not None:
        cases = cases[:limit]

    provider_inst = build_provider(
        provider,
        model=model or "",
        options=task_provider_options(
            provider,
            output_schema=[f.model_dump() for f in task.output_schema],
            system_prompt=task.system_prompt,
        ),
    )

    # Build a shared judge for llm_judge scoring rules (G-Eval style).
    judge_instance = None
    needs_judge = any(r.method == "llm_judge" for r in task.scoring_rules)
    if needs_judge:
        # No implicit judge: use the provider/model the caller selected. A
        # task's historical mock judge must not override a real selection.
        judge_cfg = JudgeConfig(
            provider=judge_provider or provider,
            model=judge_model or model,
        )
        try:
            judge_instance = build_provider(judge_cfg.provider, model=judge_cfg.model, options={})
        except Exception:
            judge_instance = None

    records: list[PredictionRecord] = []
    recorder = TraceRecorder()
    start = time.perf_counter()
    total = len(cases)

    for index, case in enumerate(cases, start=1):
        prompt = _build_task_prompt(task, case)
        with recorder.case(case.id) as trace:
            call_started = time.perf_counter()
            try:
                response = provider_inst.predict_text(prompt)  # type: ignore[attr-defined]
            except Exception as exc:
                trace.add(
                    SPAN_PROVIDER_CALL,
                    (time.perf_counter() - call_started) * 1000.0,
                    error=str(exc),
                    detail={"provider": provider, "model": provider_inst.model or provider},
                )
                records.append(
                    PredictionRecord(
                        case_id=case.id,
                        scenario_family="custom",
                        ok=False,
                        category=None,
                        requires_review=None,
                        expected_category=Category.MATCHED,
                        expected_requires_review=False,
                        correct=None,
                        raw_content=str(exc),
                        error_kind="provider_error",
                        error=str(exc),
                        latency_ms=0.0,
                    )
                )
            else:
                trace.add(
                    SPAN_PROVIDER_CALL,
                    (time.perf_counter() - call_started) * 1000.0,
                    detail={
                        "provider": provider,
                        "model": provider_inst.model or provider,
                        "reported_ms": round(response.latency_ms, 3),
                        "input_tokens": response.input_tokens,
                        "output_tokens": response.output_tokens,
                    },
                )
                # The judge runs *inside* scoring, so its span must be
                # subtracted from the score span or the waterfall double-counts.
                judge_ms = [0.0]
                judge_for_case = (
                    SpanProxyProvider(
                        judge_instance,
                        trace,
                        # Default-arg binding keeps this lambda tied to this
                        # case's accumulator rather than a later loop value.
                        on_ms=lambda ms, acc=judge_ms: acc.__setitem__(0, acc[0] + ms),
                    )
                    if judge_instance is not None
                    else None
                )
                score_started = time.perf_counter()
                score_result = _score_task_output(
                    task,
                    case.expected,
                    response.content,
                    judge_provider=judge_for_case,
                    case_input=case.input,
                    task_case=case,
                )
                score_elapsed = (time.perf_counter() - score_started) * 1000.0
                trace.add(
                    SPAN_SCORE,
                    max(0.0, score_elapsed - judge_ms[0]),
                    detail={
                        "ok": score_result["ok"],
                        "judge_ms": round(judge_ms[0], 3),
                    },
                )
                records.append(
                    PredictionRecord(
                        case_id=case.id,
                        scenario_family="custom",
                        ok=score_result["ok"],
                        category=None,
                        requires_review=None,
                        expected_category=Category.MATCHED,
                        expected_requires_review=False,
                        correct=score_result["ok"],
                        raw_content=response.content,
                        error_kind=None,
                        error=None,
                        latency_ms=response.latency_ms,
                        input_tokens=response.input_tokens,
                        output_tokens=response.output_tokens,
                    )
                )
        if on_progress:
            on_progress(index, total)

    metrics = {"n_cases": len(cases), "n_valid": sum(1 for r in records if r.ok)}
    created_at = datetime.now(UTC)
    model_slug = re.sub(r"[^a-z0-9]+", "-", (provider_inst.model or provider).lower()).strip("-") or "model"
    run_id = f"{name}-{provider}-{model_slug}-{created_at.strftime('%Y%m%dT%H%M%SZ')}"
    run_dir = (output_root or Path("runs")) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    predictions_text = "".join(r.model_dump_json() + "\n" for r in records)
    (run_dir / "predictions.jsonl").write_text(predictions_text, encoding="utf-8")
    recorder.write(run_dir)
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    manifest = {
        "run_id": run_id,
        "task": task.name,
        "task_version": task.version,
        "split": split,
        "provider": {"name": provider, "model": provider_inst.model or provider},
        "n_cases": len(cases),
        "trace": {"file": TRACE_FILENAME, "n_cases": total},
        "created_at_utc": created_at.isoformat(timespec="seconds"),
        "duration_seconds": round(time.perf_counter() - start, 3),
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return TaskRunResult(
        run_id=run_id,
        run_dir=run_dir,
        n_cases=len(cases),
        n_valid=metrics["n_valid"],
        metrics=metrics,
        manifest=manifest,
    )


__all__ = ["TaskRunResult", "run_task_experiment"]
