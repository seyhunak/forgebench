"""ForgeBench command-line interface.

Commands (each is implemented and tested before being documented):

    forgebench list-datasets
    forgebench validate-dataset finance_v1
    forgebench run --config configs/baseline.yaml
    forgebench compare runs/run-a runs/run-b
    forgebench report runs/run-a
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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
from .providers.mistral import verify_api_key
from .registry import default_datasets_root, list_datasets, validate_dataset
from .reporting import load_run, render_comparison, render_report
from .runner import run_experiment
from .schemas import PredictionRecord

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
        help="Mistral API key. Prefer the hidden prompt (args land in shell history).",
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
    """Bring your own key: save a Mistral API key to the git-ignored .env (mode 0600)."""
    if show:
        typer.echo(f"key:   {mask(get_value('MISTRAL_API_KEY'))}  [{source_of('MISTRAL_API_KEY')}]")
        typer.echo(
            f"model: {get_value('MISTRAL_MODEL') or '(not set)'}  [{source_of('MISTRAL_MODEL')}]"
        )
        env_file = find_env_file()
        typer.echo(f"file:  {env_file or '(none yet; created in the current directory on save)'}")
        return

    if clear:
        removed = delete_value("MISTRAL_API_KEY")
        if removed:
            typer.echo(f"cleared MISTRAL_API_KEY from {removed}")
        else:
            typer.echo("no saved key found; nothing to clear")
        return

    if not key:
        key = typer.prompt("Paste your Mistral API key", hide_input=True).strip()
    if not key:
        typer.echo("error: empty key, nothing saved", err=True)
        raise typer.Exit(code=1)

    target = set_value("MISTRAL_API_KEY", key)
    typer.echo(f"saved MISTRAL_API_KEY to {target} (chmod 600, git-ignored)")
    if model:
        set_value("MISTRAL_MODEL", model)
        typer.echo(f"saved MISTRAL_MODEL={model} to {target}")

    if verify:
        typer.echo("verifying against api.mistral.ai ...")
        accepted, detail = verify_api_key(key)
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
        import streamlit  # noqa: F401, PLC0415
    except ImportError as exc:
        typer.echo('error: the UI extra is not installed. Run: pip install -e ".[ui]"', err=True)
        raise typer.Exit(code=1) from exc

    app_path = Path(__file__).with_name("dashboard.py")
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.port",
        str(port),
        "--server.address",
        host,
        "--server.headless",
        "false" if open_browser else "true",
        "--browser.gatherUsageStats",
        "false",
    ]
    repo_root = Path(__file__).resolve().parents[2]
    typer.echo(f"Starting ForgeBench dashboard at http://{host}:{port}  (Ctrl-C to stop)")
    raise typer.Exit(code=subprocess.call(command, cwd=str(repo_root)))


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
        None, "--provider", help="Override provider from the config (mock | mistral)."
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


if __name__ == "__main__":  # pragma: no cover
    app()
