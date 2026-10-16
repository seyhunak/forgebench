"""ForgeBench HTTP API: FastAPI backend for the Hallmark UI.

Exposes the same functions the CLI uses (config loading, credentials,
dataset listing, run execution, run reporting) as JSON endpoints so a
frontend can drive the benchmark without Streamlit.
"""

from __future__ import annotations

import json
import re
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from .config import ExperimentConfig, load_config
from .credentials import (
    delete_value,
    find_env_file,
    get_value,
    load_env_files,
    mask,
    set_value,
    source_of,
)
from .dashboard import list_configs as _list_configs
from .dashboard import list_runs as _list_runs
from .providers import PROVIDER_ENV_VARS
from .providers.verify import verify_provider_key
from .registry import default_datasets_root, list_datasets, load_dataset, load_split
from .reporting import load_run, render_comparison, render_report
from .runner import run_experiment
from .task_runner import run_task_experiment
from .tasks import list_tasks, load_task_with_cases, validate_task

_run_state: dict[str, dict[str, Any]] = {}

_TASK_STATE_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _task_state_id(name: str, provider: str, model: str) -> str:
    """A unique, URL-safe handle for a task run's progress state.

    The name/provider/model triple alone is not unique: two models on the same
    provider (e.g. ``ministral-8b`` vs ``ministral-3b``) — or the same model run
    twice — would collide and let one run's progress overwrite another's, so a
    short random token is appended.
    """
    stem = _TASK_STATE_UNSAFE.sub("-", f"{name}-{provider}-{model or 'default'}").strip("-")
    return f"{stem}-{uuid.uuid4().hex[:8]}"


class _ProgressReporter:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id

    def __call__(self, done: int, total: int) -> None:
        _run_state[self.run_id]["progress"] = {"done": done, "total": total}


class CredentialSave(BaseModel):
    key: str
    model: str | None = None
    provider: str = "mistral"


class RunRequest(BaseModel):
    config: str
    provider: str = "mock"
    limit: int | None = None
    run_id: str | None = None
    output_root: str = "runs"


class TaskRunRequest(BaseModel):
    name: str
    split: str = "test"
    provider: str = "mock"
    model: str = ""
    judge_provider: str = ""
    judge_model: str = ""
    limit: int | None = None
    output_root: str = "runs"


class CompareRequest(BaseModel):
    run_dirs: list[str]


app = FastAPI(title="ForgeBench API", version=__version__)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = REPO_ROOT / "configs"
STATIC_DIR = Path(__file__).parent / "static"


# ---------------------------------------------------------------------------
# Config endpoints
# ---------------------------------------------------------------------------


@app.get("/api/configs")
def list_configs() -> list[dict[str, str]]:
    """All experiment YAML configs under configs/."""
    paths = _list_configs(REPO_ROOT)
    return [{"name": p.name, "path": str(p.relative_to(REPO_ROOT))} for p in paths]


@app.get("/api/configs/{config_path:path}")
def get_config(config_path: str) -> dict[str, Any]:
    """Load and validate a single experiment config."""
    full = REPO_ROOT / config_path
    if not full.exists():
        raise HTTPException(status_code=404, detail=f"config not found: {config_path}")
    try:
        cfg = load_config(full)
        return cfg.model_dump()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Credential endpoints
# ---------------------------------------------------------------------------


@app.get("/api/credentials")
def credential_status() -> dict[str, Any]:
    """Current key/mask/status without exposing the raw key."""
    load_env_files()
    key = get_value("MISTRAL_API_KEY")
    model = get_value("MISTRAL_MODEL")
    return {
        "key_set": bool(key),
        "key_masked": mask(key) if key else None,
        "source": source_of("MISTRAL_API_KEY"),
        "model": model,
        "env_file": str(find_env_file()) if find_env_file() else None,
    }


@app.post("/api/credentials")
def save_credential(payload: CredentialSave) -> dict[str, str]:
    """Save API key (+ optional default model) to .env."""
    env_var = PROVIDER_ENV_VARS.get(payload.provider, "MISTRAL_API_KEY")
    target = set_value(env_var, payload.key)
    if payload.model:
        model_var = env_var.replace("_API_KEY", "_MODEL")
        set_value(model_var, payload.model)
    return {"saved_to": str(target), "chmod": "0600", "provider": payload.provider}


@app.delete("/api/credentials")
def delete_credential() -> dict[str, str | None]:
    """Remove the saved API key."""
    removed = delete_value("MISTRAL_API_KEY")
    return {"removed_from": str(removed) if removed else None}


class CredentialVerify(BaseModel):
    provider: str = "mistral"


@app.post("/api/credentials/verify")
def verify_credential(payload: CredentialVerify) -> dict[str, Any]:
    """Check the saved key against the provider API."""
    load_env_files()
    env_var = PROVIDER_ENV_VARS.get(payload.provider, "MISTRAL_API_KEY")
    key = get_value(env_var)
    if not key:
        raise HTTPException(status_code=400, detail=f"No key saved for {env_var}.")

    accepted, detail = verify_provider_key(payload.provider, key)
    if accepted is True:
        return {"accepted": True, "detail": detail}
    if accepted is False:
        return {"accepted": False, "detail": detail}
    return {"accepted": None, "detail": detail}


# ---------------------------------------------------------------------------
# Provider endpoints
# ---------------------------------------------------------------------------


@app.get("/api/providers")
def list_providers() -> list[dict[str, Any]]:
    """Available providers with titleized display names."""
    return [
        {"id": "mock", "name": "Mock", "api_key_required": False},
        {"id": "mistral", "name": "Mistral", "api_key_required": True},
        {"id": "openai", "name": "OpenAI", "api_key_required": True},
        {"id": "anthropic", "name": "Anthropic", "api_key_required": True},
        {"id": "google", "name": "Google", "api_key_required": True},
        {"id": "openrouter", "name": "OpenRouter", "api_key_required": True},
    ]


@app.get("/api/models")
def list_models() -> dict[str, Any]:
    """All providers and models from https://models.dev/api.json."""

    models_path = STATIC_DIR / "models.json"
    if not models_path.exists():
        raise HTTPException(status_code=404, detail="models.json not found")
    with open(models_path, encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/models/{provider_id}")
def list_provider_models(provider_id: str) -> dict[str, Any]:
    """Models for a specific provider from models.dev."""

    models_path = STATIC_DIR / "models.json"
    if not models_path.exists():
        raise HTTPException(status_code=404, detail="models.json not found")
    with open(models_path, encoding="utf-8") as f:
        data = json.load(f)
    if provider_id not in data:
        raise HTTPException(status_code=404, detail=f"provider '{provider_id}' not found")
    return data[provider_id]


# ---------------------------------------------------------------------------
# Dataset endpoints
# ---------------------------------------------------------------------------


@app.get("/api/datasets")
def list_datasets_endpoint() -> list[str]:
    return list_datasets(default_datasets_root())


@app.get("/api/datasets/{name}")
def get_dataset(name: str) -> dict[str, Any]:
    """Get dataset metadata and split info."""
    try:
        cases, info = load_dataset(name, "test", default_datasets_root())
        return {
            "name": info.name,
            "version": info.version,
            "task": info.task,
            "license": info.license,
            "families": info.families,
            "splits": info.splits,
            "split_hashes": info.split_hashes,
            "n_cases": len(cases),
            "families_count": len(info.families),
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/datasets/{name}/splits/{split}")
def get_dataset_split(name: str, split: str) -> dict[str, Any]:
    """Get cases from a dataset split."""
    try:
        cases = load_split(name, split, default_datasets_root())
        return {
            "name": name,
            "split": split,
            "n_cases": len(cases),
            "cases": [c.model_dump() for c in cases],
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Run management endpoints
# ---------------------------------------------------------------------------


@app.delete("/api/runs/{run_id:path}")
def delete_run(run_id: str) -> dict[str, str]:
    """Delete a run directory."""
    runs_root = REPO_ROOT / "runs"
    run_dir = runs_root / run_id
    if not run_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
    try:
        shutil.rmtree(run_dir)
        # Clear from in-memory state if present
        _run_state.pop(run_id, None)
        return {"deleted": run_id}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Config management endpoints
# ---------------------------------------------------------------------------


@app.post("/api/configs/{config_path:path}")
def save_config(config_path: str, payload: dict[str, Any]) -> dict[str, str]:
    """Save/update an experiment config YAML file."""
    import yaml

    full = REPO_ROOT / config_path
    full.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Validate by loading
        ExperimentConfig.model_validate(payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    full.write_text(
        yaml.dump(payload, default_flow_style=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return {"saved": config_path}


# ---------------------------------------------------------------------------
# Run endpoints
# ---------------------------------------------------------------------------


@app.post("/api/run")
def start_run(payload: RunRequest) -> dict[str, str]:
    """Start a benchmark run in a background thread."""
    config_path = REPO_ROOT / payload.config
    if not config_path.exists():
        raise HTTPException(status_code=404, detail=f"config not found: {payload.config}")

    try:
        experiment = load_config(config_path)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Override provider if explicitly requested from the UI.
    if payload.provider and payload.provider != "mock":
        experiment.provider.name = payload.provider

    run_id = payload.run_id or f"{experiment.experiment.name}-{experiment.provider.name}"

    _run_state[run_id] = {
        "status": "running",
        "progress": {"done": 0, "total": 0},
        "result": None,
        "error": None,
    }

    def _worker() -> None:
        try:
            reporter = _ProgressReporter(run_id)
            result = run_experiment(
                experiment,
                output_root=Path(payload.output_root),
                limit=payload.limit,
                run_id=payload.run_id,
                on_progress=reporter,
            )
            _run_state[run_id]["status"] = "done"
            _run_state[run_id]["result"] = {
                "run_id": result.run_id,
                "run_dir": str(result.run_dir),
                "metrics": result.metrics,
                "manifest": result.manifest,
            }
        except Exception as exc:  # noqa: BLE001
            _run_state[run_id]["status"] = "error"
            _run_state[run_id]["error"] = str(exc)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    return {"run_id": run_id, "status": "started"}


@app.get("/api/run/{run_id}/progress")
def run_progress(run_id: str) -> dict[str, Any]:
    state = _run_state.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
    return state


@app.get("/api/runs")
def list_runs() -> list[dict[str, Any]]:
    """Run directories that have a manifest, newest first."""

    paths = _list_runs()
    out = []
    for p in paths:
        try:
            entry = load_run(str(p))
            out.append(
                {
                    "run_id": entry["run_id"],
                    "path": str(p.relative_to(REPO_ROOT)),
                    "provider": entry["manifest"].get("provider", {}),
                    "dataset": entry["manifest"].get("dataset", {}),
                    "metrics": entry["metrics"],
                    "created_at": entry["manifest"].get("created_at_utc"),
                }
            )
        except Exception:  # noqa: BLE001
            continue
    return out


@app.get("/api/runs/{run_id:path}/report")
def get_run_report(run_id: str) -> dict[str, str]:
    """Render the Markdown report for a run."""
    runs_root = REPO_ROOT / "runs"
    run_dir = runs_root / run_id
    if not run_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")

    from .dashboard import read_predictions

    try:
        entry = load_run(str(run_dir))
        records = read_predictions(run_dir)
        text = render_report(entry["manifest"], entry["metrics"], records)
        return {"markdown": text}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/runs/{run_id:path}/predictions")
def get_run_predictions(run_id: str) -> list[dict[str, Any]]:
    runs_root = REPO_ROOT / "runs"
    run_dir = runs_root / run_id
    if not run_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")

    from .dashboard import read_predictions

    records = read_predictions(run_dir)
    return [r.model_dump() for r in records]


@app.get("/api/runs/{run_id:path}")
def get_run(run_id: str) -> dict[str, Any]:
    """Load one run's manifest + metrics."""
    runs_root = REPO_ROOT / "runs"
    run_dir = runs_root / run_id
    if not run_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
    try:
        entry = load_run(str(run_dir))
        return entry
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Task endpoints
# ---------------------------------------------------------------------------


@app.get("/api/tasks")
def list_tasks_endpoint() -> list[str]:
    """All task names under tasks/."""
    root = Path(__file__).resolve().parents[2] / "tasks"
    return list_tasks(root)


# NOTE: registered before "/api/tasks/{name}" so the literal "runs" segment
# is not captured as a task name (which would 500 on an unknown task).
@app.get("/api/tasks/runs")
def list_task_runs() -> list[dict[str, Any]]:
    """Task run directories that have a manifest, newest first."""
    paths = _list_runs()
    out = []
    for p in paths:
        try:
            entry = load_run(str(p))
            manifest = entry["manifest"]
            if manifest.get("task"):
                out.append(
                    {
                        "run_id": entry["run_id"],
                        "path": str(p.relative_to(REPO_ROOT)),
                        "task": manifest.get("task", {}),
                        "split": manifest.get("split", ""),
                        "metrics": entry["metrics"],
                        "created_at": manifest.get("created_at_utc"),
                    }
                )
        except Exception:  # noqa: BLE001
            continue
    return out


@app.get("/api/tasks/{name}")
def validate_task_endpoint(name: str) -> dict[str, Any]:
    """Validate a task definition and its case files."""
    root = Path(__file__).resolve().parents[2] / "tasks"
    try:
        info, report = validate_task(name, root)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=f"task not found or invalid: {name}: {report.problems}",
        )
    return {
        "name": info.name,
        "version": info.version,
        "description": info.description,
        "input_fields": info.input_fields,
        "output_fields": info.output_fields,
        "scoring_methods": info.scoring_methods,
        "n_cases": info.n_cases,
        "case_hashes": info.case_hashes,
        "ok": report.ok,
        "problems": report.problems,
    }


@app.post("/api/tasks/{name}/run")
def start_task_run(name: str, payload: TaskRunRequest) -> dict[str, str]:
    """Start a custom-task evaluation run in a background thread."""
    try:
        task, _ = load_task_with_cases(name, payload.split)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    run_id = _task_state_id(name, payload.provider, payload.model)

    _run_state[run_id] = {
        "status": "running",
        "progress": {"done": 0, "total": 0},
        "result": None,
        "error": None,
        "type": "task",
    }

    def _worker() -> None:
        try:
            reporter = _ProgressReporter(run_id)
            result = run_task_experiment(
                name=name,
                split=payload.split,
                provider=payload.provider,
                model=payload.model,
                judge_provider=payload.judge_provider,
                judge_model=payload.judge_model,
                limit=payload.limit,
                output_root=Path(payload.output_root),
                on_progress=reporter,
            )
            _run_state[run_id]["status"] = "done"
            _run_state[run_id]["result"] = {
                "run_id": result.run_id,
                "run_dir": str(result.run_dir),
                "metrics": result.metrics,
                "manifest": result.manifest,
            }
        except Exception as exc:  # noqa: BLE001
            _run_state[run_id]["status"] = "error"
            _run_state[run_id]["error"] = str(exc)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    return {"run_id": run_id, "status": "started"}


# Mirrors "/api/run/{run_id}/progress" — the flat shape the UI polls after
# POST /api/tasks/{name}/run returns its run_id.
@app.get("/api/tasks/{run_id}/progress")
def task_run_progress(run_id: str) -> dict[str, Any]:
    state = _run_state.get(run_id)
    if state is None or state.get("type") != "task":
        raise HTTPException(status_code=404, detail=f"task run not found: {run_id}")
    return state


@app.post("/api/compare")
def compare_runs(payload: CompareRequest) -> dict[str, str]:
    if len(payload.run_dirs) < 2:
        raise HTTPException(status_code=400, detail="compare needs at least two run directories")
    entries = []
    for rd in payload.run_dirs:
        d = REPO_ROOT / rd
        if not d.is_dir():
            raise HTTPException(status_code=404, detail=f"run not found: {rd}")
        entries.append(load_run(str(d)))
    text = render_comparison(entries)
    return {"markdown": text}


@app.post("/api/compare/structured")
def compare_runs_structured(payload: CompareRequest) -> dict[str, Any]:
    """Return structured comparison data for UI table rendering."""
    if len(payload.run_dirs) < 2:
        raise HTTPException(status_code=400, detail="compare needs at least two run directories")
    entries = []
    for rd in payload.run_dirs:
        d = REPO_ROOT / rd
        if not d.is_dir():
            raise HTTPException(status_code=404, detail=f"run not found: {rd}")
        entries.append(load_run(str(d)))

    # Build run summaries
    runs = []
    for entry in entries:
        manifest = entry["manifest"]
        metrics = entry["metrics"]
        provider = manifest.get("provider", {})
        dataset = manifest.get("dataset", {})
        runs.append(
            {
                "run_id": entry["run_id"],
                "path": manifest.get("run_id", ""),
                "provider_name": provider.get("name", "unknown"),
                "provider_model": provider.get("model", "unknown"),
                "dataset_name": dataset.get("name", "unknown"),
                "dataset_version": dataset.get("version", "unknown"),
                "n_cases": metrics.get("n_cases", 0),
                "n_valid": metrics.get("n_valid", 0),
                "created_at": manifest.get("created_at_utc", ""),
                "metrics": metrics,
            }
        )

    # Collect all scalar metric keys
    scalar_keys: list[str] = []
    for entry in entries:
        for key, value in entry["metrics"].items():
            if (
                isinstance(value, (int, float))
                and key not in ("n_cases", "n_valid")
                and key not in scalar_keys
            ):
                scalar_keys.append(key)

    latency_keys = []
    if all(isinstance(e["metrics"].get("latency"), dict) for e in entries):
        latency_keys = ["latency.p50_ms", "latency.p95_ms"]
    cost_keys = []
    if all(isinstance(e["metrics"].get("estimated_cost"), dict) for e in entries):
        cost_keys = ["estimated_cost.usd_per_1000_cases"]

    def resolve(entry: dict[str, Any], key: str) -> float | None:
        if "." in key:
            section, sub = key.split(".", 1)
            value = entry["metrics"].get(section)
            return value.get(sub) if isinstance(value, dict) else None
        value = entry["metrics"].get(key)
        return float(value) if isinstance(value, (int, float)) else None

    # Build metric rows with deltas vs baseline (first run)
    entries[0]
    metric_rows = []
    for key in scalar_keys + latency_keys + cost_keys:
        values = [resolve(entry, key) for entry in entries]
        if any(v is None for v in values):
            continue
        label = key.replace("_", " ").title()
        delta = values[-1] - values[0] if len(values) > 1 else 0.0
        metric_rows.append(
            {
                "key": key,
                "label": label,
                "values": [round(v, 4) for v in values],
                "delta": round(delta, 4),
            }
        )

    return {"runs": runs, "metric_rows": metric_rows}


# ---------------------------------------------------------------------------
# Static UI
# ---------------------------------------------------------------------------


app.mount(
    "/static",
    StaticFiles(directory=str(STATIC_DIR)),
    name="static",
)


@app.get("/", response_class=HTMLResponse)
def ui() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
