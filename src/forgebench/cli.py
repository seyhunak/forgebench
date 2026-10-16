"""ForgeBench command-line interface.

Commands (each is implemented and tested before being documented):

    forgebench list-datasets
    forgebench validate-dataset finance_v1
    forgebench run --config configs/baseline.yaml
    forgebench compare runs/run-a runs/run-b
    forgebench report runs/run-a
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import typer

from . import __version__
from .config import load_config
from .credentials import (
    delete_value,
    find_env_file,
    get_value,
    load_env_files,
    mask,
    set_value,
    source_of,
)
from .providers import PROVIDER_ENV_VARS
from .providers.verify import verify_provider_key
from .registry import default_datasets_root, list_datasets, validate_dataset
from .reporting import load_run, render_comparison, render_report
from .runner import run_experiment
from .schemas import PredictionRecord, ScoringRule, TaskCase, TaskDefinition
from .tasks import (
    list_tasks,
    load_task,
    load_task_with_cases,
    validate_task,
)

# CLI convenience: read the nearest .env walking up from the working directory,
# without overriding variables already present in the environment.
load_env_files()

app = typer.Typer(
    name="forgebench",
    help="Measure domain adaptation, not just model intelligence.",
    no_args_is_help=True,
    add_completion=False,
)


def _root_option(value: Path | None) -> Path | None:
    return value


@app.callback()
def _main() -> None:
    """ForgeBench: reproducible, provider-agnostic LLM evaluation."""


@app.command("version")
def version_cmd() -> None:
    """Print the installed forgebench version."""
    typer.echo(__version__)


@app.command("set-key")
def set_key_cmd(
    key: str = typer.Option(
        "",
        "--key",
        help="API key. Prefer the hidden prompt (args land in shell history).",
    ),
    provider: str = typer.Option(
        "mistral",
        "--provider",
        help="Provider: mistral, openai, anthropic, google, openrouter.",
    ),
    model: str = typer.Option(
        "", "--model", help="Also save a default model id (e.g. ministral-8b-2512)."
    ),
    show: bool = typer.Option(False, "--show", help="Show current key status (masked) and exit."),
    clear: bool = typer.Option(False, "--clear", help="Delete the saved key and exit."),
    verify: bool = typer.Option(
        True, "--verify/--no-verify", help="Check the key against the API after saving."
    ),
) -> None:
    """Bring your own key: save an API key to the git-ignored .env (mode 0600)."""
    if provider == "mock":
        typer.echo("error: the mock provider needs no API key.", err=True)
        raise typer.Exit(code=1)
    env_var = PROVIDER_ENV_VARS.get(provider)
    if env_var is None:
        typer.echo(
            f"error: unknown provider '{provider}'. "
            f"Choose from: {', '.join(sorted(PROVIDER_ENV_VARS))}.",
            err=True,
        )
        raise typer.Exit(code=1)

    if show:
        typer.echo(f"key:   {mask(get_value(env_var))}  [{source_of(env_var)}]")
        model_var = env_var.replace("_API_KEY", "_MODEL")
        typer.echo(f"model: {get_value(model_var) or '(not set)'}  [{source_of(model_var)}]")
        env_file = find_env_file()
        typer.echo(f"file:  {env_file or '(none yet; created in the current directory on save)'}")
        return

    if clear:
        removed = delete_value(env_var)
        if removed:
            typer.echo(f"cleared {env_var} from {removed}")
        else:
            typer.echo(f"no saved key found for {env_var}; nothing to clear")
        return

    if not key:
        key = typer.prompt(f"Paste your {provider} API key", hide_input=True).strip()
    if not key:
        typer.echo("error: empty key, nothing saved", err=True)
        raise typer.Exit(code=1)

    target = set_value(env_var, key)
    typer.echo(f"saved {env_var} to {target} (chmod 600, git-ignored)")
    if model:
        model_var = env_var.replace("_API_KEY", "_MODEL")
        set_value(model_var, model)
        typer.echo(f"saved {model_var}={model} to {target}")

    if verify:
        typer.echo(f"verifying {provider} key ...")
        accepted, detail = verify_provider_key(provider, key)
        if accepted:
            typer.echo(f"OK: key {mask(key)} {detail}")
        elif accepted is False:
            typer.echo(f"WARNING: key {mask(key)} {detail}", err=True)
        else:
            typer.echo(f"NOTE: {detail}", err=True)
    typer.echo(
        "Run a smoke test: forgebench run --config configs/mistral_baseline.yaml "
        "--limit 5 --run-id mistral-smoke"
    )


@app.command("dashboard")
def dashboard_cmd(
    port: int = typer.Option(8501, "--port", min=1, max=65535, help="Port to serve on."),
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address (local only by default)."),
    open_browser: bool = typer.Option(
        True, "--open/--no-open", help="Open the dashboard in your default browser."
    ),
) -> None:
    """Launch the local dashboard: BYOK key entry, benchmark runs, result comparison."""
    try:
        import uvicorn  # noqa: F401, PLC0415

        from .api import app as api_app  # noqa: F401, PLC0415
    except ImportError as exc:
        typer.echo('error: the UI extra is not installed. Run: pip install -e ".[ui]"', err=True)
        raise typer.Exit(code=1) from exc

    Path(__file__).resolve().parents[2]
    typer.echo(f"Starting ForgeBench dashboard at http://{host}:{port}  (Ctrl-C to stop)")

    config = uvicorn.Config(
        api_app,
        host=host,
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    if open_browser:
        import webbrowser

        webbrowser.open(f"http://{host}:{port}/")

    asyncio.run(server.serve())


@app.command("list-datasets")
def list_datasets_cmd(
    datasets_root: Path | None = typer.Option(
        None, "--datasets-root", help="Override dataset location."
    ),
) -> None:
    """List datasets available in the registry."""
    root = datasets_root or default_datasets_root()
    names = list_datasets(root)
    if not names:
        typer.echo(f"No datasets found under {root}.")
        raise typer.Exit(code=1)
    for name in names:
        typer.echo(name)


@app.command("models")
def models_cmd(
    provider: str = typer.Option(
        "openrouter",
        "--provider",
        help="Provider: mock, mistral, openai, anthropic, google, openrouter.",
    ),
    live: bool = typer.Option(
        False,
        "--live",
        help="For OpenRouter, fetch the live catalog instead of the pinned snapshot.",
    ),
    search: str = typer.Option(
        "", "--search", help="Only show models whose id or name contains this text."
    ),
    limit: int | None = typer.Option(None, "--limit", min=1, help="Show at most N models."),
) -> None:
    """List the models a provider offers (OpenRouter has hundreds)."""
    if provider == "mock":
        typer.echo("rule-mock-v1\tRule Mock v1")
        return

    entries: list[tuple[str, str]] = []
    source = ""

    if provider == "openrouter" and live:
        from .providers.openrouter import list_models  # noqa: PLC0415

        try:
            entries = [(str(m.get("id", "")), str(m.get("name", ""))) for m in list_models()]
            source = "live catalog (openrouter.ai/api/v1/models)"
        except Exception as exc:  # noqa: BLE001 - fall back to the snapshot
            typer.echo(
                f"note: live fetch failed ({type(exc).__name__}: {exc}); using snapshot",
                err=True,
            )

    if not entries:
        snapshot = Path(__file__).resolve().parent / "static" / "models.json"
        if not snapshot.exists():
            typer.echo("error: models.json snapshot not found.", err=True)
            raise typer.Exit(code=1)
        data = json.loads(snapshot.read_text(encoding="utf-8"))
        if provider not in data:
            typer.echo(
                f"error: unknown provider '{provider}'. Known: {', '.join(sorted(data))}.",
                err=True,
            )
            raise typer.Exit(code=1)
        entries = [
            (m.get("id", ""), m.get("name", m.get("id", "")))
            for m in data[provider].get("models", {}).values()
        ]
        source = "models.dev snapshot"

    if search:
        needle = search.lower()
        entries = [(i, n) for i, n in entries if needle in i.lower() or needle in n.lower()]
    entries.sort()
    if limit is not None:
        entries = entries[:limit]

    typer.echo(f"# {len(entries)} model(s) — {source}")
    if not entries:
        typer.echo(f"no models matched '{search}' for {provider}.")
    for model_id, name in entries:
        typer.echo(f"{model_id}\t{name}")


@app.command("validate-dataset")
def validate_dataset_cmd(
    name: str = typer.Argument(..., help="Dataset name, e.g. finance_v1."),
    datasets_root: Path | None = typer.Option(
        None, "--datasets-root", help="Override dataset location."
    ),
) -> None:
    """Validate a dataset: schema, ids, splits, families, class distribution."""
    report = validate_dataset(name, _root_option(datasets_root))
    typer.echo(f"dataset: {report.name}")
    for split, count in report.counts.items():
        typer.echo(f"  {split}: {count} cases")
    typer.echo(f"  class distribution: {json.dumps(report.class_distribution)}")
    if report.ok:
        typer.echo("OK: dataset is valid.")
        return
    for problem in report.problems:
        typer.echo(f"PROBLEM: {problem}")
    raise typer.Exit(code=1)


@app.command("task-list")
def task_list_cmd(
    tasks_root: Path | None = typer.Option(
        None, "--tasks-root", help="Override task directory location."
    ),
) -> None:
    """List available custom task definitions."""
    tasks = list_tasks(tasks_root)
    if not tasks:
        typer.echo("No tasks found. Create tasks under tasks/<name>/task.yaml")
        return
    typer.echo("Available tasks:")
    for name in tasks:
        try:
            task = load_task(name, tasks_root)
            typer.echo(f"  {name} (v{task.version}) — {task.description or '(no description)'}")
        except Exception as exc:
            typer.echo(f"  {name} — error loading: {exc}", err=True)


@app.command("task-validate")
def task_validate_cmd(
    name: str = typer.Argument(..., help="Task name to validate."),
    tasks_root: Path | None = typer.Option(
        None, "--tasks-root", help="Override task directory location."
    ),
) -> None:
    """Validate a custom task definition and its case files."""
    try:
        info, report = validate_task(name, tasks_root)
    except FileNotFoundError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Task: {info.name} v{info.version}")
    typer.echo(f"Description: {info.description or '(none)'}")
    typer.echo(f"Input fields: {', '.join(info.input_fields)}")
    typer.echo(f"Output fields: {', '.join(info.output_fields)}")
    typer.echo(f"Scoring: {', '.join(info.scoring_methods)}")
    typer.echo(f"Cases: {info.n_cases}")
    if report.ok:
        typer.echo("Status: VALID")
    else:
        typer.echo("Status: INVALID", err=True)
        for problem in report.problems:
            typer.echo(f"  - {problem}", err=True)
        raise typer.Exit(code=1)


@app.command("task-run")
def task_run_cmd(
    name: str = typer.Argument(..., help="Task name to run."),
    split: str = typer.Option("test", "--split", help="Dataset split to evaluate."),
    provider: str = typer.Option(
        "mock",
        "--provider",
        help="Provider name (mock, mistral, openai, anthropic, google, openrouter).",
    ),
    model: str = typer.Option("", "--model", help="Model ID (overrides provider default)."),
    limit: int | None = typer.Option(
        None, "--limit", min=1, help="Evaluate only the first N cases."
    ),
    tasks_root: Path | None = typer.Option(
        None, "--tasks-root", help="Override task directory location."
    ),
    output_root: Path | None = typer.Option(
        None, "--output-root", help="Where to write run artifacts."
    ),
    judge_provider: str = typer.Option(
        "",
        "--judge-provider",
        help="Judge provider override (mock, mistral, openai, anthropic, google, openrouter).",
    ),
    judge_model: str = typer.Option(
        "", "--judge-model", help="Judge model override (e.g. gpt-4o-mini)."
    ),
) -> None:
    """Run a custom task evaluation end-to-end."""
    try:
        task, cases = load_task_with_cases(name, split, tasks_root)
    except FileNotFoundError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if limit is not None:
        cases = cases[:limit]

    typer.echo(f"Task: {task.name} v{task.version}")
    typer.echo(f"Split: {split} ({len(cases)} cases)")
    typer.echo(f"Provider: {provider}")

    import time
    from datetime import UTC, datetime

    from .providers import build_provider, task_provider_options
    from .schemas import Category, PredictionRecord

    provider_inst = build_provider(
        provider,
        model=model or "",
        options=task_provider_options(
            provider,
            output_schema=[f.model_dump() for f in task.output_schema],
            system_prompt=task.system_prompt,
        ),
    )

    records: list[PredictionRecord] = []
    start = time.perf_counter()

    # Build a shared judge for llm_judge scoring rules (G-Eval style).
    judge_instance = None
    needs_judge = any(r.method == "llm_judge" for r in task.scoring_rules)
    if needs_judge:
        from .schemas import JudgeConfig

        judge_cfg = JudgeConfig(
            provider=judge_provider or task.judge.provider,
            model=judge_model or task.judge.model,
        )
        try:
            judge_instance = build_provider(judge_cfg.provider, model=judge_cfg.model, options={})
        except Exception as exc:
            typer.echo(f"warning: judge unavailable ({exc}); llm_judge rules will fail", err=True)
    for index, case in enumerate(cases, start=1):
        prompt = _build_task_prompt(task, case)
        output_schema = [f.model_dump() for f in task.output_schema]
        try:
            if provider == "mock":
                response = provider_inst.predict_text(  # type: ignore[attr-defined]
                    prompt, output_schema=output_schema
                )
            else:
                response = provider_inst.predict_text(prompt)  # type: ignore[attr-defined]
        except Exception as exc:
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
            score_result = _score_task_output(
                task,
                case.expected,
                response.content,
                judge_provider=judge_instance,
                case_input=case.input,
                task_case=case,
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
        if index % 25 == 0 or index == len(cases):
            typer.echo(f"  {index}/{len(cases)} cases")

    metrics = {"n_cases": len(cases), "n_valid": sum(1 for r in records if r.ok)}
    created_at = datetime.now(UTC)
    run_id = f"{name}-{provider}-{created_at.strftime('%Y%m%dT%H%M%SZ')}"
    run_dir = (output_root or Path("runs")) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    import json

    (run_dir / "predictions.jsonl").write_text(
        "".join(r.model_dump_json() + "\n" for r in records), encoding="utf-8"
    )
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    manifest = {
        "run_id": run_id,
        "task": task.name,
        "task_version": task.version,
        "split": split,
        "provider": {"name": provider_inst.model, "model": provider_inst.model},
        "n_cases": len(cases),
        "created_at_utc": created_at.isoformat(timespec="seconds"),
        "duration_seconds": round(time.perf_counter() - start, 3),
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    typer.echo(f"\nRun: {run_id}")
    typer.echo(f"Cases: {metrics['n_cases']} ({metrics['n_valid']} valid)")
    typer.echo(f"Artifacts: {run_dir.resolve()}")


@app.command("run")
def run_cmd(
    config: Path = typer.Option(..., "--config", "-c", help="Experiment config YAML."),
    run_id: str | None = typer.Option(
        None, "--run-id", help="Output directory name (default: name-provider-timestamp)."
    ),
    limit: int | None = typer.Option(
        None, "--limit", min=1, help="Evaluate only the first N cases (smoke test)."
    ),
    output_root: Path = typer.Option(
        Path("runs"), "--output-root", help="Where run artifacts are written."
    ),
    datasets_root: Path | None = typer.Option(
        None, "--datasets-root", help="Override dataset location."
    ),
    provider: str | None = typer.Option(
        None, "--provider", help="Override provider from the config (e.g. mistral, openrouter)."
    ),
    model: str | None = typer.Option(
        None, "--model", help="Override the model id from the config."
    ),
) -> None:
    """Run one experiment and write predictions, metrics, manifest, and report."""
    try:
        experiment = load_config(config)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if provider:
        experiment.provider.name = provider
    if model:
        experiment.provider.model = model

    def progress(done: int, total: int) -> None:
        if done % 25 == 0 or done == total:
            typer.echo(f"  {done}/{total} cases")

    try:
        result = run_experiment(
            experiment,
            datasets_root=_root_option(datasets_root),
            output_root=output_root,
            limit=limit,
            run_id=run_id,
            on_progress=progress,
        )
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    metrics = result.metrics
    typer.echo("")
    typer.echo(f"run:     {result.run_id}")
    typer.echo(f"cases:   {metrics['n_cases']} ({metrics['n_valid']} schema-valid)")
    typer.echo(f"accuracy:                {metrics.get('accuracy', 0):.4f}")
    typer.echo(f"macro_f1:                {metrics.get('macro_f1', 0):.4f}")
    typer.echo(f"critical_false_match_rate: {metrics.get('critical_false_match_rate', 0):.4f}")
    typer.echo(f"escalation_recall:       {metrics.get('escalation_recall', 0):.4f}")
    typer.echo(f"schema_validity:         {metrics.get('schema_validity', 0):.4f}")
    typer.echo(f"artifacts: {result.run_dir.resolve()}")


@app.command("compare")
def compare_cmd(
    run_dirs: list[Path] = typer.Argument(
        ..., help="Two or more run directories; the first is the baseline."
    ),
    out: Path | None = typer.Option(
        None, "--out", help="Write the comparison Markdown to this file."
    ),
) -> None:
    """Compare runs produced by `forgebench run`."""
    if len(run_dirs) < 2:
        typer.echo("error: compare needs at least two run directories", err=True)
        raise typer.Exit(code=2)
    try:
        entries = [load_run(str(path)) for path in run_dirs]
    except FileNotFoundError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    text = render_comparison(entries)
    if out:
        out.write_text(text, encoding="utf-8")
        typer.echo(f"wrote {out.resolve()}")
    else:
        typer.echo(text)


@app.command("report")
def report_cmd(
    run_dir: Path = typer.Argument(..., help="A directory produced by `forgebench run`."),
    out: Path | None = typer.Option(None, "--out", help="Write the report Markdown to this file."),
) -> None:
    """(Re)generate the Markdown report for an existing run."""
    try:
        entry = load_run(str(run_dir))
    except FileNotFoundError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    predictions_path = Path(run_dir) / "predictions.jsonl"
    records: list[PredictionRecord] = []
    if predictions_path.exists():
        for line in predictions_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(PredictionRecord.model_validate_json(line))
    text = render_report(entry["manifest"], entry["metrics"], records)
    if out:
        out.write_text(text, encoding="utf-8")
        typer.echo(f"wrote {out.resolve()}")
    else:
        typer.echo(text)


def _build_task_prompt(task: TaskDefinition, case: TaskCase) -> str:
    """Build a prompt from task definition and case input."""
    lines: list[str] = []
    if task.system_prompt:
        lines.append(f"System: {task.system_prompt}")
    lines.append("Task: Evaluate the following input and return JSON matching the output schema.")
    lines.append("")
    lines.append("Input fields:")
    for field in task.input_fields:
        value = case.input.get(field, "")
        lines.append(f"  {field}: {value}")
    lines.append("")
    lines.append("Output schema:")
    for field in task.output_schema:
        enum_info = f" (enum: {', '.join(field.enum_values)})" if field.enum_values else ""
        lines.append(f"  {field.name} ({field.type}){enum_info}: {field.description}")
    lines.append("")
    lines.append("Scoring rules:")
    for rule in task.scoring_rules:
        lines.append(f"  {rule.field}: {rule.method} (weight={rule.weight})")
    lines.append("")
    lines.append("Return valid JSON only.")
    return "\n".join(lines)


def _score_task_output(
    task: TaskDefinition,
    expected: dict,
    raw_output: str,
    *,
    judge_provider: Any = None,
    case_input: dict | None = None,
    task_case: Any = None,
) -> dict:
    """Score a raw model output against expected values using scoring rules."""
    import json

    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError:
        return {"ok": False}

    all_pass = True
    for rule in task.scoring_rules:
        expected_val = expected.get(rule.field)
        actual_val = parsed.get(rule.field)
        if not _apply_scoring_rule(
            rule.method,
            expected_val,
            actual_val,
            rule.threshold,
            rule=rule,
            task=task,
            judge_provider=judge_provider,
            case_input=case_input,
            task_case=task_case,
        ):
            all_pass = False
    return {"ok": all_pass}


def _apply_scoring_rule(  # noqa: PLR0911
    method: str,
    expected: Any,
    actual: Any,
    threshold: float | None,
    *,
    rule: ScoringRule | None = None,
    task: TaskDefinition | None = None,
    judge_provider: Any = None,
    case_input: dict | None = None,
    task_case: Any = None,
) -> bool:
    if method == "exact_match":
        return expected == actual
    if method == "boolean":
        return bool(expected) == bool(actual)
    if method == "contains":
        if isinstance(expected, str) and isinstance(actual, str):
            return expected.lower() in actual.lower()
        return str(expected) == str(actual)
    if method == "f1":
        if isinstance(expected, list) and isinstance(actual, list):
            set_e = set(expected)
            set_a = set(actual)
            if not set_e and not set_a:
                return True
            if not set_e or not set_a:
                return False
            intersection = len(set_e & set_a)
            precision = intersection / len(set_a)
            recall = intersection / len(set_e)
            if precision + recall == 0:
                return False
            f1 = 2 * precision * recall / (precision + recall)
            return f1 >= (threshold or 0.5)
        return expected == actual
    if method == "llm_judge":
        return _apply_llm_judge(
            expected,
            actual,
            threshold,
            rule=rule,
            task=task,
            judge_provider=judge_provider,
            case_input=case_input,
        )
    if method in ("faithfulness", "answer_relevancy", "contextual_relevancy"):
        return _apply_rag_metric(
            method,
            actual,
            threshold,
            rule=rule,
            task=task,
            judge_provider=judge_provider,
            case_input=case_input,
            task_case=task_case,
        )
    return False


def _apply_rag_metric(
    method: str,
    actual: Any,
    threshold: float | None,
    *,
    rule: ScoringRule | None = None,
    task: TaskDefinition | None = None,
    judge_provider: Any = None,
    case_input: dict | None = None,
    task_case: Any = None,
) -> bool:
    """Deterministic lexical RAG metrics (DeepEval RAGAS-style, offline-first).

    - faithfulness: share of the answer grounded in retrieval_context.
    - answer_relevancy: vocab overlap between answer and question.
    - contextual_relevancy: share of retrieved chunks relevant to the question.

    Falls back to an LLM judge when no retrieval context is available but a
    judge is configured.
    """
    from .metrics.rag import (
        contextual_relevancy,
        lexical_answer_relevancy,
        lexical_faithfulness,
    )

    retrieval_context: list[str] = []
    if task_case is not None:
        retrieval_context = list(getattr(task_case, "retrieval_context", None) or [])
    question = ""
    if task is not None and case_input:
        first_field = task.input_fields[0] if task.input_fields else None
        if first_field and first_field in case_input:
            question = str(case_input[first_field])
        else:
            question = " ".join(str(v) for v in case_input.values())
    answer_text = actual if isinstance(actual, str) else str(actual)

    if method == "faithfulness":
        if not retrieval_context and judge_provider is not None:
            return _apply_llm_judge(
                retrieval_context,
                answer_text,
                threshold,
                rule=rule,
                task=task,
                judge_provider=judge_provider,
                case_input=case_input,
            )
        score = lexical_faithfulness(answer_text, retrieval_context)
    elif method == "answer_relevancy":
        score = lexical_answer_relevancy(answer_text, question)
    elif method == "contextual_relevancy":
        score = contextual_relevancy(retrieval_context, question)
    else:
        return False
    return score >= (threshold if threshold is not None else 0.5)


def _apply_llm_judge(
    expected: Any,
    actual: Any,
    threshold: float | None,
    *,
    rule: ScoringRule | None = None,
    task: TaskDefinition | None = None,
    judge_provider: Any = None,
    case_input: dict | None = None,
) -> bool:
    """G-Eval-style subjective scoring via any configured judge provider."""
    from .judge import build_judge_prompt, call_judge

    criterion = (
        rule.criteria if rule and rule.criteria else None
    ) or "Determine whether the model output for field matches the expected value."
    evaluation_steps = (
        rule.evaluation_steps
        if rule and rule.evaluation_steps
        else [
            "Compare the actual output against the expected output.",
            "Score highly when meaning and key details match; "
            "heavily penalize contradictions and omissions.",
            "Vague but non-contradicting phrasing is acceptable.",
        ]
    )
    input_text = None
    if case_input:
        input_text = "\n".join(f"{k}: {v}" for k, v in case_input.items())
    prompt = build_judge_prompt(
        criterion,
        input_text=input_text,
        actual_output=actual,
        expected_output=expected,
        evaluation_steps=evaluation_steps,
    )
    if judge_provider is None:
        from .providers import build_provider
        from .schemas import JudgeConfig

        cfg = task.judge if task and task.judge else JudgeConfig()
        judge_provider = build_provider(cfg.provider, model=cfg.model, options={})
    try:
        from .providers.base import ProviderError

        score, verdict, _reason, _resp = call_judge(_JudgeShim(judge_provider), prompt)
    except ProviderError:
        return False
    cutoff = threshold if threshold is not None else 0.5
    return verdict and score >= cutoff


class _JudgeShim:
    """Adapt a ModelProvider's predict_text into the judge module's protocol."""

    def __init__(self, provider: Any) -> None:
        self._provider = provider
        self.name = getattr(provider, "name", "judge")

    def predict_text(self, prompt: str):  # type: ignore[no-untyped-def]
        from .judge import JUDGE_SYSTEM_PROMPT

        return self._provider.predict_text(prompt, JUDGE_SYSTEM_PROMPT)


if __name__ == "__main__":  # pragma: no cover
    app()
