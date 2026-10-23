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
from .prompts import (
    PromptNotFound,
    load_prompt,
    prompt_catalog,
    save_prompt_version,
    set_label,
)
from .providers import DEFAULT_PROVIDER, PROVIDER_ENV_VARS
from .providers.verify import verify_provider_key
from .registry import default_datasets_root, list_datasets, validate_dataset
from .reporting import load_run, render_comparison, render_report
from .runner import run_experiment
from .schemas import PredictionRecord, ScoringRule, TaskCase, TaskDefinition
from .tasks import (
    list_tasks,
    load_case_inputs,
    load_task,
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
        DEFAULT_PROVIDER,
        "--provider",
        help="Provider: openrouter, google, anthropic, openai, ollama, mistral.",
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
        help="Provider: mock, mistral, openai, anthropic, google, openrouter, ollama.",
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

    if provider == "ollama":
        from .providers.ollama import list_local_models  # noqa: PLC0415

        try:
            entries = [(m["id"], m["name"]) for m in list_local_models()]
            source = "ollama daemon (/api/tags)"
        except Exception as exc:  # noqa: BLE001 - daemon may be down
            typer.echo(f"error: {type(exc).__name__}: {exc}", err=True)
            raise typer.Exit(code=1) from exc

    if provider == "openrouter" and live and not entries:
        from .providers.openrouter import list_models  # noqa: PLC0415

        try:
            entries = [(str(m.get("id", "")), str(m.get("name", ""))) for m in list_models()]
            source = "live catalog (openrouter.ai/api/v1/models)"
        except Exception as exc:  # noqa: BLE001 - fall back to the snapshot
            typer.echo(
                f"note: live fetch failed ({type(exc).__name__}: {exc}); using snapshot",
                err=True,
            )

    if provider == "ollama" and not entries:
        typer.echo("# 0 model(s) — ollama daemon (no models pulled)")
        return

    if not entries and provider != "ollama":
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


@app.command("prompt-list")
def prompt_list_cmd(
    prompts_root: Path | None = typer.Option(
        None, "--prompts-root", help="Override prompt registry location."
    ),
) -> None:
    """List versioned prompts in the registry."""
    entries = prompt_catalog(_root_option(prompts_root))
    if not entries:
        typer.echo("No prompts yet. Create one with: forgebench prompt-save <name> --file body.md")
        return
    for entry in entries:
        labels = ", ".join(f"{k}={v}" for k, v in entry["labels"].items()) or "-"
        typer.echo(
            f"  {entry['name']}  latest=v{entry['latest']}  "
            f"versions={len(entry['versions'])}  labels={labels}  "
            f"sha256={entry['latest_sha256'][:12]}"
        )


@app.command("prompt-show")
def prompt_show_cmd(
    name: str = typer.Argument(..., help="Prompt name."),
    version: int | None = typer.Option(
        None, "--version", "-v", min=1, help="Version (default: latest)."
    ),
    prompts_root: Path | None = typer.Option(
        None, "--prompts-root", help="Override prompt registry location."
    ),
) -> None:
    """Print one prompt version (body first, metadata to stderr)."""
    try:
        prompt = load_prompt(name, version, root=_root_option(prompts_root))
    except (PromptNotFound, ValueError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"# {prompt.name}@v{prompt.version}  sha256={prompt.sha256[:12]}  "
        f"{prompt.chars} chars  labels={','.join(prompt.labels) or '-'}",
        err=True,
    )
    if prompt.note:
        typer.echo(f"# note: {prompt.note}", err=True)
    typer.echo(prompt.body)


@app.command("prompt-save")
def prompt_save_cmd(
    name: str = typer.Argument(..., help="Prompt name."),
    file: Path | None = typer.Option(
        None, "--file", "-f", help="File to read the body from (default: stdin)."
    ),
    note: str = typer.Option("", "--note", help="Why this version exists."),
    label: str = typer.Option("", "--label", help="Also point this label at the new version."),
    prompts_root: Path | None = typer.Option(
        None, "--prompts-root", help="Override prompt registry location."
    ),
) -> None:
    """Write a new immutable version of a prompt."""
    body = file.read_text(encoding="utf-8") if file is not None else typer.prompt("prompt body")
    if not body.strip():
        typer.echo("error: empty prompt body", err=True)
        raise typer.Exit(code=1)
    try:
        prompt = save_prompt_version(name, body, note=note, root=_root_option(prompts_root))
    except (ValueError, OSError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"saved {prompt.name}@v{prompt.version}  sha256={prompt.sha256[:12]}  {prompt.chars} chars"
    )
    if label:
        set_label(name, label, prompt.version, root=_root_option(prompts_root))
        typer.echo(f"label '{label}' -> v{prompt.version}")


@app.command("prompt-label")
def prompt_label_cmd(
    name: str = typer.Argument(..., help="Prompt name."),
    label: str = typer.Argument(..., help="Label to move, e.g. production."),
    version: int = typer.Argument(..., min=1, help="Version to point at (0 removes the label)."),
    prompts_root: Path | None = typer.Option(
        None, "--prompts-root", help="Override prompt registry location."
    ),
) -> None:
    """Point a label at a version (version 0 removes the label)."""
    root = _root_option(prompts_root)
    try:
        labels = set_label(name, label, None if version == 0 else version, root=root)
    except (PromptNotFound, ValueError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if labels:
        typer.echo("labels: " + ", ".join(f"{k}=v{v}" for k, v in sorted(labels.items())))
    else:
        typer.echo("labels: (none)")


@app.command("safety-scan")
def safety_scan_cmd(
    split: str = typer.Option("test", "--split", help="Dataset split to evaluate."),
    provider: str = typer.Option(
        DEFAULT_PROVIDER,
        "--provider",
        help="Provider name (mistral, openai, anthropic, google, openrouter, ollama, mock).",
    ),
    model: str = typer.Option("", "--model", help="Model ID (overrides provider default)."),
    limit: int | None = typer.Option(
        None, "--limit", min=1, help="Evaluate only the first N cases."
    ),
    output_root: Path | None = typer.Option(
        None, "--output-root", help="Where to write run artifacts."
    ),
) -> None:
    """Run the safety red-team task (prompt injection, jailbreak, PII, bias, toxicity)."""
    task_run_cmd(
        name="safety_redteam",
        split=split,
        provider=provider,
        model=model,
        limit=limit,
        output_root=output_root,
    )


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
    name: str | None = typer.Argument(
        None, help="Task name to run. Omit (or pass --all) to run every task."
    ),
    split: str = typer.Option("test", "--split", help="Dataset split to evaluate."),
    provider: str = typer.Option(
        DEFAULT_PROVIDER,
        "--provider",
        help="Provider name (mistral, openai, anthropic, google, openrouter, ollama, mock).",
    ),
    model: str = typer.Option("", "--model", help="Model ID (overrides provider default)."),
    models: str = typer.Option(
        "",
        "--models",
        help=(
            'Comma-separated model ids to compare, e.g. "model-a,model-b". '
            "Adds a comparison matrix run on top of each single run."
        ),
    ),
    tasks: str = typer.Option(
        "",
        "--tasks",
        help='Comma-separated task names to run (e.g. "email_classification,ticket_triage").',
    ),
    all_tasks: bool = typer.Option(
        False, "--all", "--all-tasks", help="Run every available task under --tasks-root."
    ),
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
        help="Judge provider: one of mistral/openai/anthropic/google/openrouter/ollama/mock.",
    ),
    judge_model: str = typer.Option(
        "", "--judge-model", help="Judge model override (e.g. gpt-4o-mini)."
    ),
) -> None:
    """Run a custom task evaluation end-to-end (or compare several models).

    Every model produces the same artifacts as a single run
    (predictions, metrics, manifest, report, trace). With two or more models
    the first run is the baseline and a ``comparison.md`` lands next to it.
    """

    # Direct function calls (safety-scan delegates here) pass typer's
    # OptionInfo defaults instead of plain strings — normalize them first.
    def _as_text(value: Any, default: str) -> str:
        if isinstance(value, str):
            return value
        return str(getattr(value, "default", default) or default)

    models = _as_text(models, "")
    tasks = _as_text(tasks, "")
    if not isinstance(all_tasks, bool):
        all_tasks = bool(getattr(all_tasks, "default", False))
    judge_provider = _as_text(judge_provider, "")
    judge_model = _as_text(judge_model, "")
    if tasks_root is not None and not isinstance(tasks_root, Path):
        default_root = getattr(tasks_root, "default", None)
        tasks_root = default_root if isinstance(default_root, Path) else None
    if output_root is not None and not isinstance(output_root, Path):
        default_out = getattr(output_root, "default", None)
        output_root = default_out if isinstance(default_out, Path) else None

    model_list = [m.strip() for m in models.split(",") if m.strip()]
    if model and model not in model_list:
        model_list.insert(0, model)
    if not model_list:
        model_list = [""]

    if provider == "mock" or judge_provider == "mock":
        typer.echo("note: mock provider — offline pipeline validation, not a real model.")

    from .task_runner import run_task_experiment

    def _progress(done: int, total: int) -> None:
        if done % 25 == 0 or done == total:
            typer.echo(f"  {done}/{total} cases")

    # Resolve which tasks to run.
    from .tasks import list_tasks

    selected_tasks: list[str] = []
    if tasks.strip():
        selected_tasks = [t.strip() for t in tasks.split(",") if t.strip()]
    elif all_tasks or name is None:
        selected_tasks = list_tasks(tasks_root)
    elif name:
        selected_tasks = [name]

    if not selected_tasks:
        typer.echo("error: no tasks to run (pass a task name, --tasks, or --all).", err=True)
        raise typer.Exit(code=1)

    suite_entries: list[dict[str, Any]] = []
    for task_name in selected_tasks:
        typer.echo(f"\n=== Task: {task_name} ===")
        entries: list[dict[str, Any]] = []
        for model_id in model_list:
            try:
                result = run_task_experiment(
                    name=task_name,
                    split=split,
                    provider=provider,
                    model=model_id,
                    judge_provider=judge_provider,
                    judge_model=judge_model,
                    limit=limit,
                    tasks_root=tasks_root,
                    output_root=output_root,
                    on_progress=_progress,
                )
            except FileNotFoundError as exc:
                typer.echo(f"error: {exc}", err=True)
                raise typer.Exit(code=1) from exc
            entries.append(load_run(str(result.run_dir)))
            suite_entries.append(entries[-1])
            typer.echo(f"\nRun: {result.run_id}")
            typer.echo(f"Cases: {result.metrics['n_cases']} ({result.metrics['n_valid']} valid)")
            typer.echo(f"Artifacts: {result.run_dir.resolve()}")

        if len(entries) >= 2:
            comparison = render_comparison(entries)
            comparison_path = entries[0]["manifest"].get("run_id")
            out_dir = Path(output_root or Path("runs")) / str(comparison_path)
            (out_dir / "comparison.md").write_text(comparison, encoding="utf-8")
            typer.echo("")
            typer.echo(comparison.rstrip())
            typer.echo(f"comparison: {(out_dir / 'comparison.md').resolve()}")

    # Write a small suite summary when more than one task ran.
    if len(selected_tasks) > 1:
        summary_path = Path(output_root or Path("runs")) / "suite_summary.md"
        lines = ["# ForgeBench operations suite", ""]
        lines.append("| Task | Run | Model | Cases | Valid | Score |")
        lines.append("| --- | --- | --- | ---: | ---: | ---: |")
        for e in suite_entries:
            m = e["manifest"]
            met = e["metrics"]
            score = met.get("accuracy")
            if score is None:
                score = met.get("valid_rate")
            lines.append(
                f"| {m.get('task')} | `{m.get('run_id')}` | "
                f"{(m.get('provider') or {}).get('model')} | {met.get('n_cases')} | "
                f"{met.get('n_valid')} | {'-' if score is None else f'{score:.4f}'} |"
            )
        lines.append("")
        try:
            summary_path.write_text("\n".join(lines), encoding="utf-8")
            typer.echo(f"\nsuite summary: {summary_path.resolve()}")
        except OSError:
            pass


# Automation-friendly aliases for running the whole operations suite.
app.command("run-suite")(task_run_cmd)
app.command("run-all")(task_run_cmd)
app.command("automate")(task_run_cmd)
app.command("run-tasks")(task_run_cmd)


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


@app.command("history")
def history_cmd(
    runs_root: Path = typer.Option(Path("runs"), "--runs-root", help="Where runs live."),
    limit: int | None = typer.Option(None, "--limit", min=1, help="Show only the N most recent."),
) -> None:
    """Chronological trend of every run, grouped by task/dataset."""
    from .history import collect_history, render_history

    entries = collect_history(runs_root)
    if limit is not None:
        entries = entries[-limit:]
    typer.echo(render_history(entries))


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
    case_inputs = load_case_inputs(entry["manifest"], Path(run_dir))
    text = render_report(entry["manifest"], entry["metrics"], records, case_inputs=case_inputs)
    if out:
        out.write_text(text, encoding="utf-8")
        typer.echo(f"wrote {out.resolve()}")
    else:
        typer.echo(text)


@app.command("export")
def export_cmd(
    run_dir: Path = typer.Argument(
        ..., help="A directory produced by `forgebench run` or `forgebench task-run`."
    ),
    format: str = typer.Option("json", "--format", "-f", help="Export format: json, csv or html."),
    out: Path | None = typer.Option(
        None, "--out", "-o", help="Write to this file (default: stdout)."
    ),
) -> None:
    """Export a run's predictions and metrics to JSON, CSV, or a standalone HTML report."""
    import csv
    import io

    run_dir = Path(run_dir)
    predictions_path = run_dir / "predictions.jsonl"
    records: list[dict[str, Any]] = []
    if predictions_path.exists():
        for line in predictions_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(PredictionRecord.model_validate_json(line).model_dump())

    metrics = {}
    metrics_path = run_dir / "metrics.json"
    if metrics_path.exists():
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))

    manifest = {}
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    fmt = format.lower()
    if fmt == "json":
        payload = {"manifest": manifest, "metrics": metrics, "predictions": records}
        text = json.dumps(payload, indent=2, default=str)
    elif fmt == "csv":
        if not records:
            text = ""
        else:
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=list(records[0].keys()))
            writer.writeheader()
            for r in records:
                writer.writerow({k: ("" if v is None else v) for k, v in r.items()})
            text = buf.getvalue()
    elif fmt == "html":
        import html as _html

        from bleach import clean
        from markdown_it import MarkdownIt
        from mdit_py_plugins.gfm import gfm_plugin

        parsed_records: list[PredictionRecord] = []
        if predictions_path.exists():
            for line in predictions_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    parsed_records.append(PredictionRecord.model_validate_json(line))
        markdown_text = render_report(
            manifest,
            metrics,
            parsed_records,
            case_inputs=load_case_inputs(manifest, run_dir),
        )
        md = MarkdownIt(config="commonmark", options_update={"sanitize": True})
        md.use(gfm_plugin)
        html_body = clean(
            md.render(markdown_text),
            tags={
                "h1",
                "h2",
                "h3",
                "p",
                "ul",
                "ol",
                "li",
                "table",
                "thead",
                "tbody",
                "tr",
                "th",
                "td",
                "em",
                "strong",
                "code",
                "br",
                "hr",
                "blockquote",
                "del",
            },
            strip=True,
        )
        run_title = _html.escape(str(manifest.get("run_id", "run") or "run"))
        text = (
            "<!doctype html>\n"
            '<html lang="en"><head><meta charset="utf-8">\n'
            f"<title>ForgeBench report: {run_title}</title>\n"
            "<style>\n"
            "body{font-family:-apple-system,'Segoe UI',sans-serif;max-width:980px;"
            "margin:2rem auto;padding:0 1rem;color:#1a1a1a;line-height:1.55}"
            "h1,h2,h3{line-height:1.2}code{background:#f2f2f2;padding:0 4px;border-radius:3px;"
            "font-size:.92em}"
            "table{border-collapse:collapse;width:100%;margin:.75rem 0;font-size:.92rem}"
            "th,td{border:1px solid #ddd;padding:6px 10px;text-align:left}"
            "th{background:#f7f7f7}tr:nth-child(even) td{background:#fcfcfc}"
            "blockquote{border-left:3px solid #ddd;margin:1rem 0;padding:.25rem 1rem;color:#555}"
            "</style></head>\n"
            f"<body>\n{html_body}\n</body></html>\n"
        )
    else:
        typer.echo(f"error: unknown format {format!r}; use json, csv or html", err=True)
        raise typer.Exit(code=1)

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
    rule_scores: dict[str, bool] = {}
    for rule in task.scoring_rules:
        expected_val = expected.get(rule.field)
        actual_val = parsed.get(rule.field)
        passed = _apply_scoring_rule(
            rule.method,
            expected_val,
            actual_val,
            rule.threshold,
            rule=rule,
            task=task,
            judge_provider=judge_provider,
            case_input=case_input,
            task_case=task_case,
        )
        if not passed:
            all_pass = False
        rule_scores[rule.field] = passed
    return {"ok": all_pass, "rule_scores": rule_scores}


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
    """Deterministic lexical RAG metrics (RAGAS-style, offline-first).

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
        # No implicit judge: fail this criterion rather than quietly scoring
        # with the offline mock provider.
        return False
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
        # Prompt-only call: the judge instructions already live inside the
        # prompt body (build_judge_prompt), so shims stay compatible with any
        # provider / proxy signature (a positional second argument can break
        # wrappers like SpanProxyProvider).
        return self._provider.predict_text(prompt)


@app.command("credits")
def credits_cmd() -> None:
    """Show the local credit balance, mode and recent grants."""
    from .credits import status

    state = status()
    balance = "unlimited" if state["unlimited"] else str(state["balance"])
    typer.echo(f"mode:     {state['mode']}")
    typer.echo(
        f"balance:  {balance} credits  "
        "(1 credit = $0.10 · benchmark run 30 credits flat · task run 1 credit per case)"
    )
    typer.echo(f"ledger:   {state['ledger']}")
    for grant in state["grants"]:
        amount = "unlimited" if grant["unlimited"] else f"{grant['credits']} credits"
        typer.echo(f"granted:  {grant['code']}  {grant['package']}  {amount}  {grant['at']}")


@app.command("redeem")
def redeem_cmd(
    code: str = typer.Argument(..., help="Voucher code, e.g. FB-STARTER-50-AB12CD34."),
    service: str = typer.Option(
        "",
        "--service",
        help="Credit service URL (default FORGEBENCH_CREDITS_SERVICE or 127.0.0.1:8583).",
    ),
) -> None:
    """Redeem a voucher code from the Stripe credit fulfillment service."""
    from .credits import redeem

    try:
        state = redeem(code, service_url=service or None)
    except Exception as exc:  # noqa: BLE001 — network/service errors surface here
        typer.echo(f"redeem failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    balance = "unlimited" if state["unlimited"] else str(state["balance"])
    typer.echo(f"redeemed: {code}")
    typer.echo(f"package:  {state.get('package', '')}")
    typer.echo(f"balance:  {balance} credits")


if __name__ == "__main__":  # pragma: no cover
    app()
