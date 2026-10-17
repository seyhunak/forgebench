"""ForgeBench HTTP API: FastAPI backend for the Hallmark UI.

Exposes the same functions the CLI uses (config loading, credentials,
dataset listing, run execution, run reporting) as JSON endpoints so a
frontend can drive the benchmark without Streamlit.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any

from bleach import clean
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from markdown_it import MarkdownIt
from mdit_py_plugins.gfm import gfm_plugin
from pydantic import BaseModel, Field

from . import __version__
from .config import ExperimentConfig, load_config
from .credentials import (
    delete_value,
    env_file_values,
    find_env_file,
    get_value,
    load_env_files,
    mask,
    set_value,
    source_of,
)
from .dashboard import list_configs as _list_configs
from .dashboard import list_runs as _list_runs
from .ollama_probe import ollama_status
from .prompts import (
    PromptNotFound,
    load_prompt,
    prompt_catalog,
    save_prompt_version,
    set_label,
)
from .providers import DEFAULT_PROVIDER, PROVIDER_ENV_VARS
from .providers.verify import ollama_verdict, verify_provider_key
from .registry import default_datasets_root, list_datasets, load_dataset, load_split
from .regression import (
    clear_baseline,
    compare_runs,
    list_baselines,
    pin_baseline,
    run_dataset_name,
)
from .reporting import load_run, render_comparison, render_report
from .runner import run_experiment
from .task_runner import run_task_experiment
from .tasks import list_tasks, load_task_with_cases, validate_task
from .tracing import read_traces, summarise_traces

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
    provider: str = DEFAULT_PROVIDER


class RunRequest(BaseModel):
    config: str
    provider: str = ""
    limit: int | None = None
    run_id: str | None = None
    output_root: str = "runs"


class TaskRunRequest(BaseModel):
    name: str
    split: str = "test"
    provider: str = ""
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


# HTML tags allowed in the rendered report (whitelist for XSS prevention).
ALLOWED_HTML_TAGS = {
    # Text formatting
    "strong",
    "b",
    "em",
    "i",
    "code",
    "s",
    "u",
    # Headings
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    # Lists
    "ul",
    "ol",
    "li",
    # Tables
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    # Paragraphs and line breaks
    "p",
    "br",
    "hr",
    # Blockquotes and code blocks
    "blockquote",
    "pre",
    "div",
    # Links and spans
    "a",
    "span",
    # Images (src is sanitized by the renderer)
    "img",
}


def _resolve_run_dir(run_id: str) -> Path | None:
    """Resolve a run identifier to its directory, or ``None``.

    The dashboard sends the repo-relative path (``runs/<id>``); the historical
    API form is the bare directory name (``<id>``). Both are accepted, and the
    result must stay inside ``runs/`` so a crafted id cannot escape it.
    """
    runs_root = (REPO_ROOT / "runs").resolve()
    for candidate in (REPO_ROOT / run_id, runs_root / run_id):
        resolved = candidate.resolve()
        if resolved.is_dir() and (resolved == runs_root or runs_root in resolved.parents):
            return resolved
    return None


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

#: Dashboard provider order. OpenRouter leads so it is the default selection.
#: Mock is deliberately absent — it needs no key, so it never belonged in a
#: credentials list; it stays available to the CLI and configs. Ollama closes
#: the list: selectable for BYOK and local models, not runnable yet.
_PROVIDER_LABELS: dict[str, str] = {
    "openrouter": "OpenRouter",
    "mistral": "Mistral",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google",
    "ollama": "Ollama",
}


def _env_var_for(provider: str) -> str:
    """Credential env var for a provider, tolerant of unknown names."""
    return PROVIDER_ENV_VARS.get(provider, PROVIDER_ENV_VARS[DEFAULT_PROVIDER])


def _configured_provider() -> str:
    """First provider (OpenRouter first) that actually has a key, else the default."""
    for pid in _PROVIDER_LABELS:
        if get_value(PROVIDER_ENV_VARS[pid]):
            return pid
    return DEFAULT_PROVIDER


def _configured_model(provider_id: str) -> str:
    """Default model saved in credentials for ``provider_id`` (if any)."""
    env_var = _env_var_for(provider_id)
    return (get_value(env_var.replace("_API_KEY", "_MODEL")) or "").strip()


def _remember(name: str, value: str | None) -> None:
    """Keep the process environment in step with a ``.env`` write or removal.

    ``get_value`` prefers the process environment and ``load_env_files`` never
    overrides it, so a key saved while the server runs would otherwise be
    shadowed by whatever was loaded at startup.
    """
    if value:
        os.environ[name] = value
    else:
        os.environ.pop(name, None)


@app.get("/api/credentials")
def credential_status(provider: str | None = None) -> dict[str, Any]:
    """Current key/mask/status without exposing the raw key.

    Without ``provider`` the panel reports the first provider with a key
    configured (OpenRouter first), falling back to the default provider.
    """
    load_env_files()
    provider_id = provider or _configured_provider()
    env_var = _env_var_for(provider_id)
    model = get_value(env_var.replace("_API_KEY", "_MODEL"))
    key = get_value(env_var)
    return {
        "provider": provider_id,
        "key_set": bool(key),
        "key_masked": mask(key) if key else None,
        "source": source_of(env_var),
        "model": model,
        "env_file": str(find_env_file()) if find_env_file() else None,
    }


@app.post("/api/credentials")
def save_credential(payload: CredentialSave) -> dict[str, str]:
    """Save API key (+ optional default model) to .env."""
    env_var = _env_var_for(payload.provider)
    target = set_value(env_var, payload.key)
    _remember(env_var, payload.key)
    if payload.model:
        model_var = env_var.replace("_API_KEY", "_MODEL")
        set_value(model_var, payload.model)
        _remember(model_var, payload.model)
    return {"saved_to": str(target), "chmod": "0600", "provider": payload.provider}


@app.delete("/api/credentials")
def delete_credential(provider: str = DEFAULT_PROVIDER) -> dict[str, str | None]:
    """Remove the saved API key for one provider."""
    env_var = _env_var_for(provider)
    removed = delete_value(env_var)
    _remember(env_var, None)
    return {
        "removed_from": str(removed) if removed else None,
        "provider": provider,
    }


class CredentialVerify(BaseModel):
    provider: str = DEFAULT_PROVIDER


@app.post("/api/credentials/verify")
def verify_credential(payload: CredentialVerify) -> dict[str, Any]:
    """Check the saved key against the provider API — or the daemon, for Ollama.

    ``presented`` (``ok`` / ``error``) tells the frontend how to show an
    ``accepted: None`` verdict: informational status rather than a failed
    verification. Only Ollama sets it today.
    """
    load_env_files()
    env_var = _env_var_for(payload.provider)
    key = get_value(env_var)
    # Local Ollama needs no key: its check is the daemon, reported either way.
    if not key and payload.provider != "ollama":
        raise HTTPException(status_code=400, detail=f"No key saved for {env_var}.")

    if payload.provider == "ollama":
        accepted, detail, presented = ollama_verdict()
        return {"accepted": accepted, "detail": detail, "presented": presented}

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
    """Providers for the dashboard selectors: OpenRouter first (default).

    Two flags keep the UI honest:

    * ``api_key_required`` — false for Ollama, whose local models need no key.
    * ``runnable`` — false while a provider has no run adapter yet (Ollama is
      key storage + local model listing only), so the Tasks view filters it
      out and never offers a run that would fail with "unknown provider".
    """
    return [
        {
            "id": pid,
            "name": name,
            "api_key_required": pid != "ollama",
            "runnable": True,
        }
        for pid, name in _PROVIDER_LABELS.items()
    ]


@app.get("/api/ollama/status")
def ollama_status_endpoint() -> dict[str, Any]:
    """Is Ollama installed/running, and which models are pulled locally?"""
    return ollama_status()


# ---------------------------------------------------------------------------
# Environment endpoints (the Setup view)
# ---------------------------------------------------------------------------

#: BYOK rows on the Setup screen, in the order the user fills them in: the
#: default first, then the majors, then local Ollama, then the rest. This is
#: key *storage*, not runnability — an entry here may have no adapter yet
#: (ollama); the runner still refuses it with "unknown provider".
_SETUP_ORDER: tuple[str, ...] = (
    "openrouter",
    "google",
    "anthropic",
    "openai",
    "ollama",
    "mistral",
)

#: Display names for Setup rows. Runnable providers keep the same names in
#: ``_PROVIDER_LABELS`` (the API key view); ollama is storage-only.
_SETUP_LABELS: dict[str, str] = {
    "openrouter": "OpenRouter",
    "google": "Google",
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "ollama": "Ollama",
    "mistral": "Mistral",
}

#: Optional note rendered next to a row's variable name.
_SETUP_HINTS: dict[str, str] = {"ollama": "local — key optional"}

#: Variable names ForgeBench will read or write: letters, digits, underscore.
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def _env_source(name: str, stored: dict[str, str | None], is_set: bool) -> str:
    """``environment``, ``file`` or ``not_set`` — where the value is read from.

    ``source_of`` reports "environment" for anything already loaded from ``.env``
    at startup, so the file contents are consulted directly instead.
    """
    if not is_set:
        return "not_set"
    return "file" if name in stored else "environment"


class EnvVar(BaseModel):
    name: str = Field(
        pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,63}$",
        description="Environment variable name, e.g. OPENROUTER_API_KEY.",
    )
    value: str = Field(description="Value to store in the git-ignored .env file.")


@app.get("/api/env")
def list_env() -> dict[str, Any]:
    """Every provider credential variable, plus any other variable in ``.env``.

    Values are never returned raw — only masked — so the endpoint is safe to
    drive from the browser.
    """
    load_env_files()
    env_file = find_env_file()
    stored = env_file_values(env_file)

    known: set[str] = set()
    providers: list[dict[str, Any]] = []
    for pid in _SETUP_ORDER:
        key_var = PROVIDER_ENV_VARS[pid]
        model_var = key_var.replace("_API_KEY", "_MODEL")
        known.update({key_var, model_var})
        key = get_value(key_var)
        providers.append(
            {
                "provider": pid,
                "label": _SETUP_LABELS[pid],
                "key_var": key_var,
                "model_var": model_var,
                "key_set": bool(key),
                "key_masked": mask(key),
                "key_source": _env_source(key_var, stored, bool(key)),
                "model": get_value(model_var) or "",
                "hint": _SETUP_HINTS.get(pid, ""),
            }
        )

    custom = sorted(
        (
            {"name": name, "masked": mask(value), "source": _env_source(name, stored, True)}
            for name, value in stored.items()
            if name not in known
        ),
        key=lambda item: item["name"],
    )

    return {
        "env_file": str(env_file) if env_file else None,
        "providers": providers,
        "custom": custom,
    }


@app.post("/api/env")
def save_env(payload: EnvVar) -> dict[str, str]:
    """Upsert one variable in the ``.env`` file (created 0600, git-ignored)."""
    target = set_value(payload.name, payload.value)
    _remember(payload.name, payload.value)
    return {"name": payload.name, "saved_to": str(target)}


@app.delete("/api/env")
def delete_env(name: str) -> dict[str, str | None]:
    """Remove one variable from the ``.env`` file."""
    if not _ENV_NAME_RE.fullmatch(name):
        raise HTTPException(status_code=400, detail=f"invalid variable name: {name!r}")
    removed = delete_value(name)
    _remember(name, None)
    return {"name": name, "removed_from": str(removed) if removed else None}


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
# Prompt registry endpoints
# ---------------------------------------------------------------------------


class PromptCreate(BaseModel):
    """A new immutable version of a registry prompt."""

    body: str = Field(min_length=1, description="Full system-prompt body.")
    note: str = Field(default="", description="Why this version exists.")
    label: str = Field(default="", description="Optional label to move onto it.")


class PromptLabelUpdate(BaseModel):
    label: str = Field(min_length=1, description="e.g. production")
    version: int | None = Field(default=None, ge=1, description="null removes the label.")


@app.get("/api/prompts")
def list_prompts_endpoint() -> list[dict[str, Any]]:
    """Every prompt in the registry: versions, labels, latest digest."""
    return prompt_catalog()


@app.get("/api/prompts/{name}")
def get_prompt_endpoint(name: str, version: int | None = None) -> dict[str, Any]:
    """One prompt version (default: latest) with its body and provenance."""
    try:
        return load_prompt(name, version).to_dict()
    except (PromptNotFound, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/prompts/{name}", status_code=201)
def create_prompt_version(name: str, payload: PromptCreate) -> dict[str, Any]:
    """Write the next version. Versions are immutable: this never overwrites."""
    try:
        prompt = save_prompt_version(name, payload.body, note=payload.note)
        if payload.label:
            set_label(name, payload.label, prompt.version)
    except (PromptNotFound, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return prompt.to_dict()


@app.put("/api/prompts/{name}/labels")
def put_prompt_label(name: str, payload: PromptLabelUpdate) -> dict[str, Any]:
    """Move (or remove) a named pointer such as ``production``."""
    try:
        labels = set_label(name, payload.label, payload.version)
    except PromptNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"name": name, "labels": labels}


# ---------------------------------------------------------------------------
# Regression endpoints (baseline pins + case-level deltas)
# ---------------------------------------------------------------------------


class BaselinePinRequest(BaseModel):
    dataset: str = Field(min_length=1, description="Dataset the pin belongs to.")
    run_id: str = Field(min_length=1, description="Run directory name (or runs/<id>).")


def _runs_root() -> Path:
    return REPO_ROOT / "runs"


@app.get("/api/baselines")
def list_baselines_endpoint() -> dict[str, Any]:
    """Pinned baseline per dataset (local state; runs/ is git-ignored)."""
    return list_baselines(_runs_root())


@app.post("/api/baselines", status_code=201)
def pin_baseline_endpoint(payload: BaselinePinRequest) -> dict[str, Any]:
    """Pin a run as the baseline its dataset is compared against."""
    run_dir = _resolve_run_dir(payload.run_id)
    if run_dir is None:
        raise HTTPException(status_code=404, detail=f"run not found: {payload.run_id}")
    return pin_baseline(payload.dataset, run_dir, _runs_root())


@app.delete("/api/baselines/{dataset}")
def clear_baseline_endpoint(dataset: str) -> dict[str, Any]:
    """Remove the pin for one dataset."""
    if not clear_baseline(dataset, _runs_root()):
        raise HTTPException(status_code=404, detail=f"no baseline pinned for {dataset}")
    return {"dataset": dataset, "cleared": True}


@app.get("/api/runs/{run_id:path}/regression")
def get_run_regression(run_id: str, baseline: str | None = None) -> dict[str, Any]:
    """Case-level deltas between a run and its baseline.

    ``baseline`` may name any run; without it the pin for this run's dataset is
    used. No pin and no explicit baseline is a 404 with a message that says
    what to do, not a stack trace.
    """
    run_dir = _resolve_run_dir(run_id)
    if run_dir is None:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")

    baseline_dir: Path | None = None
    if baseline:
        baseline_dir = _resolve_run_dir(baseline)
        if baseline_dir is None:
            raise HTTPException(status_code=404, detail=f"baseline run not found: {baseline}")
    else:
        dataset = run_dataset_name(run_dir)
        pin = list_baselines(_runs_root()).get(dataset or "")
        if pin:
            baseline_dir = _resolve_run_dir(str(pin.get("run_id", "")))
        if baseline_dir is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"no baseline pinned for dataset '{dataset or 'unknown'}' — "
                    "pin one with POST /api/baselines {dataset, run_id}"
                ),
            )

    if baseline_dir.resolve() == run_dir.resolve():
        raise HTTPException(status_code=400, detail="baseline and candidate are the same run")

    return compare_runs(baseline_dir, run_dir).to_dict()


# ---------------------------------------------------------------------------
# Run management endpoints
# ---------------------------------------------------------------------------


@app.delete("/api/runs/{run_id:path}")
def delete_run(run_id: str) -> dict[str, str]:
    """Delete a run directory."""
    run_dir = _resolve_run_dir(run_id)
    if run_dir is None:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
    try:
        shutil.rmtree(run_dir)
        # Clear from in-memory state if present (either identifier form).
        _run_state.pop(run_id, None)
        _run_state.pop(run_dir.name, None)
        return {"deleted": run_dir.name}
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

    # Resolve the provider from the request or, failing that, from the
    # credentials section (the user's selected default). Mock is never chosen
    # implicitly: an empty request uses the configured provider.
    requested_provider = (payload.provider or "").strip() or _configured_provider()
    # No run may end up on the mock provider: an explicit mock config or
    # request is upgraded to the selected provider.
    if experiment.provider.name == "mock" or requested_provider == "mock":
        if requested_provider == "mock":
            requested_provider = _configured_provider()
    if requested_provider and requested_provider != experiment.provider.name:
        experiment.provider.name = requested_provider
    if experiment.provider.name == "mock":
        experiment.provider.name = _configured_provider()

    # Keep the provider and its configured default model in sync. A switch of
    # provider (or a missing/unusable model left over from a mock config) would
    # otherwise send an invalid model id such as ``rule-mock-v1`` to the API.
    model = experiment.provider.model
    if experiment.provider.name != "mock":
        if not model or model == "rule-mock-v1":
            model = _configured_model(experiment.provider.name)
        if model:
            experiment.provider.model = model

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
    run_dir = _resolve_run_dir(run_id)
    if run_dir is None:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")

    from .dashboard import read_predictions

    try:
        entry = load_run(str(run_dir))
        records = read_predictions(run_dir)
        text = render_report(entry["manifest"], entry["metrics"], records)
        # Render markdown to HTML for proper display in the UI.
        # Use the GFM plugin (with table support) and sanitize the output.
        # sanitize=True strips any raw HTML (e.g. scripts) injected via dataset/
        # /generator content, preventing XSS while keeping valid HTML.
        md = MarkdownIt(config="commonmark", options_update={"sanitize": True})
        md.use(gfm_plugin)
        html = md.render(text)
        # Bleach-sanitize the output to allow only safe HTML tags.
        html = clean(html, tags=ALLOWED_HTML_TAGS, strip=True)
        return {"markdown": text, "html": html}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/runs/{run_id:path}/predictions")
def get_run_predictions(run_id: str) -> list[dict[str, Any]]:
    run_dir = _resolve_run_dir(run_id)
    if run_dir is None:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")

    from .dashboard import read_predictions

    records = read_predictions(run_dir)
    return [r.model_dump() for r in records]


@app.get("/api/runs/{run_id:path}/trace")
def get_run_trace(run_id: str) -> dict[str, Any]:
    """Per-case span waterfall: how each case spent its wall-clock time.

    Runs written before tracing existed have no ``trace.jsonl``; they return an
    empty list rather than a 404 so the modal's Trace tab degrades gracefully.
    """
    run_dir = _resolve_run_dir(run_id)
    if run_dir is None:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")

    traces = read_traces(run_dir)
    return {"run_id": run_id, "summary": summarise_traces(traces), "traces": traces}


@app.get("/api/runs/{run_id:path}")
def get_run(run_id: str) -> dict[str, Any]:
    """Load one run's manifest + metrics."""
    run_dir = _resolve_run_dir(run_id)
    if run_dir is None:
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


@app.delete("/api/tasks/runs")
def delete_task_runs() -> dict[str, Any]:
    """Delete every task-run directory (never benchmark runs)."""
    deleted: list[str] = []
    for p in _list_runs():
        try:
            entry = load_run(str(p))
        except Exception:  # noqa: BLE001 - not a readable task run
            continue
        if not entry["manifest"].get("task"):
            continue
        shutil.rmtree(p)
        deleted.append(p.name)
    # Drop any in-memory progress slots that belong to deleted runs.
    for run_id in deleted:
        _run_state.pop(run_id, None)
    return {"deleted": deleted, "count": len(deleted)}


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

    # Resolve the provider/model from the credentials section when the request
    # does not name them, so the task runner never falls back to Mock/empty.
    provider = (payload.provider or "").strip() or _configured_provider()
    model = (payload.model or "").strip() or _configured_model(provider)

    judge_provider = (payload.judge_provider or "").strip()
    if not judge_provider:
        judge_provider = provider
    judge_model = (payload.judge_model or "").strip()
    if not judge_model:
        judge_model = _configured_model(judge_provider) or model

    run_id = _task_state_id(name, provider, model)

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
                provider=provider,
                model=model,
                judge_provider=judge_provider,
                judge_model=judge_model,
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
def compare_runs_markdown(payload: CompareRequest) -> dict[str, str]:
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
