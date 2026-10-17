"""API route wiring: exercised without starting an HTTP server.

The FastAPI app is an optional (``[ui]``) dependency, so these tests skip when
it is not installed rather than failing a plain ``[dev]`` environment.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi import HTTPException  # noqa: E402
from starlette.routing import Match  # noqa: E402

from forgebench.api import _task_state_id, app, validate_task_endpoint  # noqa: E402


def _paths() -> list[str]:
    return [getattr(route, "path", "") for route in app.routes]


def _matched(path: str, method: str = "GET") -> str | None:
    """The path Starlette would select: the first route with a full match."""
    scope = {"type": "http", "method": method, "path": path, "headers": []}
    for route in app.routes:
        if route.matches(scope)[0] == Match.FULL:
            return getattr(route, "path", "")
    return None


def test_task_runs_route_is_registered_before_task_name_route() -> None:
    """``/api/tasks/runs`` must win over ``/api/tasks/{name}``.

    Routes match in registration order, so if the dynamic route comes first the
    literal ``runs`` segment is captured as a task name and the request 500s.
    """
    paths = _paths()
    assert "/api/tasks/runs" in paths
    assert "/api/tasks/{name}" in paths
    assert paths.index("/api/tasks/runs") < paths.index("/api/tasks/{name}")


def test_unknown_task_returns_404_not_500() -> None:
    with pytest.raises(HTTPException) as excinfo:
        validate_task_endpoint("definitely-not-a-task")
    assert excinfo.value.status_code == 404


def test_openrouter_is_an_offered_provider() -> None:
    from forgebench.api import list_providers

    ids = [p["id"] for p in list_providers()]
    assert "openrouter" in ids


def test_openrouter_model_catalog_is_available() -> None:
    """The pinned models.dev snapshot ships the full OpenRouter catalog."""
    from forgebench.api import list_provider_models

    data = list_provider_models("openrouter")
    assert data["name"] == "OpenRouter"
    assert len(data["models"]) > 100
    # Namespaced ids are what the adapter sends as `model`.
    assert any("/" in model_id for model_id in data["models"])


def test_task_progress_route_matches_what_the_ui_polls() -> None:
    """The UI polls ``GET /api/tasks/{run_id}/progress`` after starting a run.

    A shape mismatch here is a silent dead-end in the browser ("Progress poll
    failed: Not Found"), because the poll error becomes an inline message
    rather than a crash. Keep it in lockstep with the config-run route.
    """
    assert "/api/tasks/{run_id}/progress" in _paths()
    assert "/api/run/{run_id}/progress" in _paths()
    assert (
        _matched("/api/tasks/sentiment_analysis-mistral-abc12345/progress")
        == "/api/tasks/{run_id}/progress"
    )


def test_task_progress_route_does_not_shadow_task_validation() -> None:
    assert _matched("/api/tasks/runs") == "/api/tasks/runs"
    assert _matched("/api/tasks/sentiment_analysis") == "/api/tasks/{name}"


def test_task_state_ids_are_unique_per_model_and_run() -> None:
    """Two models on one provider must not share a progress slot."""
    eight = _task_state_id("sentiment_analysis", "mistral", "ministral-8b-latest")
    three = _task_state_id("sentiment_analysis", "mistral", "ministral-3b-latest")
    again = _task_state_id("sentiment_analysis", "mistral", "ministral-8b-latest")

    assert eight != three, "different models collided"
    assert eight != again, "repeat run of the same model collided"
    assert eight.startswith("sentiment_analysis-mistral-ministral-8b-latest-")
    # Path-safe even when the model id contains slashes (e.g. OpenRouter ids).
    assert "/" not in _task_state_id("t", "openrouter", "meta-llama/llama-3-70b")


def test_start_task_run_executes_both_models_when_model_2_is_set(monkeypatch) -> None:
    """``model_2`` makes the worker evaluate a second model under the same
    run handle so two models can be benchmarked against one task split."""
    import time

    import forgebench.api as api
    from forgebench.api import TaskRunRequest
    from forgebench.task_runner import TaskRunResult

    calls: list[str] = []

    def fake(name, split, provider, model, judge_provider, judge_model, limit, output_root, on_progress):
        calls.append(model)
        for i in (1, 2):
            on_progress(i, 2)
        return TaskRunResult(
            run_id=f"{name}-{provider}-{model}-T",
            run_dir=Path("runs") / "fake",
            n_cases=2,
            n_valid=2,
            metrics={"n_cases": 2, "n_valid": 2},
            manifest={"task": name, "task_version": "1.0.0", "split": split,
                      "provider": {"name": provider, "model": model}},
        )

    monkeypatch.setattr(api, "run_task_experiment", fake)
    api._run_state.clear()

    out = api.start_task_run("summarization_qa", TaskRunRequest(
        name="summarization_qa", split="test", provider="ollama",
        model="nemotron-3-nano:4b", model_2="gpt-oss:20b-cloud"))
    assert out["status"] == "started"
    assert out["run_id_2"] and out["run_id_2"] != out["run_id"]

    state = None
    for _ in range(200):
        st = api._run_state.get(out["run_id"])
        if st and st["status"] != "running":
            state = st
            break
        time.sleep(0.01)
    assert state is not None and state["status"] == "done"
    assert state["progress"]["done"] == state["progress"]["total"] == 4

    result = state["result"]
    assert len(result["runs"]) == 2
    assert [r["model"] for r in result["runs"]] == ["nemotron-3-nano:4b", "gpt-oss:20b-cloud"]
    assert [c for c in calls] == ["nemotron-3-nano:4b", "gpt-oss:20b-cloud"]
    assert result["run_id"] == result["runs"][0]["run_id"]
    assert result["run_id_2"] == result["runs"][1]["run_id"]


def test_start_task_run_single_model_unchanged(monkeypatch) -> None:
    """Without ``model_2`` the run behaves as before (one model, no run_id_2)."""
    import forgebench.api as api
    from forgebench.api import TaskRunRequest
    from forgebench.task_runner import TaskRunResult

    def fake(name, split, provider, model, judge_provider, judge_model, limit, output_root, on_progress):
        on_progress(2, 2)
        return TaskRunResult(
            run_id=f"{name}-{provider}-{model}-T",
            run_dir=Path("runs") / "fake",
            n_cases=2, n_valid=2,
            metrics={"n_cases": 2, "n_valid": 2},
            manifest={"task": name, "task_version": "1.0.0", "split": split,
                      "provider": {"name": provider, "model": model}},
        )

    monkeypatch.setattr(api, "run_task_experiment", fake)
    api._run_state.clear()

    out = api.start_task_run("summarization_qa", TaskRunRequest(
        name="summarization_qa", split="test", provider="ollama", model="nemotron-3-nano:4b"))
    assert out["run_id_2"] is None

    import time
    state = None
    for _ in range(200):
        st = api._run_state.get(out["run_id"])
        if st and st["status"] != "running":
            state = st
            break
        time.sleep(0.01)
    assert state is not None and state["status"] == "done"
    assert len(state["result"]["runs"]) == 1


# ---------------------------------------------------------------------------
# Setup view: environment variables
# ---------------------------------------------------------------------------


def test_env_routes_are_registered_for_read_write_delete() -> None:
    assert "/api/env" in _paths()
    assert _matched("/api/env") == "/api/env"
    assert _matched("/api/env", "POST") == "/api/env"
    assert _matched("/api/env", "DELETE") == "/api/env"


def test_env_var_model_accepts_real_names_and_rejects_the_rest() -> None:
    from pydantic import ValidationError

    from forgebench.api import EnvVar

    saved = EnvVar(name="OPENROUTER_API_KEY", value="sk-or-v1-placeholder")
    assert saved.name == "OPENROUTER_API_KEY"

    for bad in ("9LEADING_DIGIT", "has space", "has-dash", "", "a" * 65):
        with pytest.raises(ValidationError):
            EnvVar(name=bad, value="x")


def test_delete_env_refuses_names_that_are_not_variables() -> None:
    """Names reach the .env line format, so anything unusual is a 400, not a write."""
    from forgebench.api import delete_env

    for bad in ("../../etc/passwd", "A B", "A=B", ""):
        with pytest.raises(HTTPException) as excinfo:
            delete_env(bad)
        assert excinfo.value.status_code == 400


def test_env_source_reports_where_a_value_is_read_from() -> None:
    """``source_of`` cannot tell file-loaded keys apart, so ``.env`` is checked directly."""
    from forgebench.api import _env_source

    assert _env_source("UNSET_VAR", {}, False) == "not_set"
    assert _env_source("SHELL_ONLY", {}, True) == "environment"
    assert _env_source("IN_FILE", {"IN_FILE": "value"}, True) == "file"


def test_setup_lists_byok_providers_in_the_requested_order() -> None:
    """The Setup screen asks for keys as a list: openrouter → … → mistral."""
    from forgebench.api import list_env

    providers = list_env()["providers"]
    assert [p["provider"] for p in providers] == [
        "openrouter",
        "google",
        "anthropic",
        "openai",
        "ollama",
        "mistral",
    ]
    for row in providers:
        assert row["key_var"].endswith("_API_KEY")
        assert row["model_var"].endswith("_MODEL")
        assert row["label"]


def test_setup_ollama_row_is_storage_only_with_a_hint() -> None:
    """Ollama: key storage + local models, now runnable via the local adapter."""
    from forgebench.api import list_env, list_providers

    ollama = next(p for p in list_env()["providers"] if p["provider"] == "ollama")
    assert ollama["key_var"] == "OLLAMA_API_KEY"
    assert ollama["model_var"] == "OLLAMA_MODEL"
    assert "key optional" in ollama["hint"]

    # Offered in the Provider selector (BYOK, no key required for local use),
    # now runnable, so the Tasks view offers it like any other adapter.
    offered = {p["id"]: p for p in list_providers()}
    assert "ollama" in offered
    assert offered["ollama"]["api_key_required"] is False
    assert offered["ollama"]["runnable"] is True


def test_provider_selector_drops_mock_and_keeps_order() -> None:
    """Mock needs no key — it is out of the selectors; Ollama takes its place."""
    from forgebench.api import list_providers

    ids = [p["id"] for p in list_providers()]
    assert "mock" not in ids
    assert ids == ["openrouter", "mistral", "openai", "anthropic", "google", "ollama"]
    # Every other entry stays a runnable, key-requiring provider.
    for p in list_providers():
        if p["id"] != "ollama":
            assert p["runnable"] is True
            assert p["api_key_required"] is True


def test_ollama_status_endpoint_reports_without_raising() -> None:
    """The install check must answer even with no Ollama at all."""
    assert "/api/ollama/status" in _paths()

    from forgebench.api import ollama_status_endpoint

    status = ollama_status_endpoint()
    assert set(status) >= {"binary", "installed", "running", "host", "models", "detail"}
    assert isinstance(status["running"], bool)
    assert isinstance(status["installed"], bool)
    assert isinstance(status["models"], list)
    assert all(isinstance(name, str) for name in status["models"])


def test_verify_ollama_is_a_daemon_check_with_presentation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify for Ollama reports daemon state; 'presented' says how to show it."""
    from forgebench import api
    from forgebench.api import CredentialVerify, verify_credential

    monkeypatch.setattr(api, "ollama_verdict", lambda: (None, "daemon is running", "ok"))
    assert verify_credential(CredentialVerify(provider="ollama")) == {
        "accepted": None,
        "detail": "daemon is running",
        "presented": "ok",
    }

    monkeypatch.setattr(api, "ollama_verdict", lambda: (None, "not reachable", "error"))
    assert verify_credential(CredentialVerify(provider="ollama"))["presented"] == "error"


def test_verify_ollama_needs_no_saved_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Local Ollama needs no key — verify must not 400 when none is saved."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)

    from forgebench import api
    from forgebench.api import CredentialVerify, verify_credential

    monkeypatch.setattr(api, "ollama_verdict", lambda: (None, "not reachable", "error"))
    assert verify_credential(CredentialVerify(provider="ollama"))["accepted"] is None


def test_verify_without_a_key_is_still_a_400_for_keyed_providers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)

    from forgebench.api import CredentialVerify, verify_credential

    with pytest.raises(HTTPException) as excinfo:
        verify_credential(CredentialVerify(provider="mistral"))
    assert excinfo.value.status_code == 400


def test_setup_never_offers_the_mock_provider() -> None:
    """Mock needs no key, so it must not take up a row on Setup."""
    from forgebench.api import list_env

    assert "mock" not in [p["provider"] for p in list_env()["providers"]]


def test_trace_route_is_registered_before_the_run_catch_all() -> None:
    """``/trace`` must win over ``/api/runs/{run_id:path}`` or it 404s.

    Routes match in registration order, and ``{run_id:path}`` swallows
    everything — so the check that matters is which route Starlette actually
    selects for a GET.
    """
    paths = _paths()
    assert "/api/runs/{run_id:path}/trace" in paths
    assert _matched("/api/runs/some-run/trace", "GET") == "/api/runs/{run_id:path}/trace"


def test_trace_of_an_unknown_run_is_a_404() -> None:
    from forgebench.api import get_run_trace

    with pytest.raises(HTTPException) as excinfo:
        get_run_trace("definitely-not-a-run")
    assert excinfo.value.status_code == 404


def test_trace_of_a_run_without_a_trace_file_is_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Runs written before tracing existed degrade to an empty trace, not a 500."""
    from forgebench import api
    from forgebench.api import get_run_trace

    run_dir = tmp_path / "legacy-run"
    run_dir.mkdir()
    monkeypatch.setattr(api, "_resolve_run_dir", lambda run_id: run_dir)

    payload = get_run_trace("legacy-run")

    assert payload["traces"] == []
    assert payload["summary"] == {"n_cases": 0}


def test_prompt_endpoints_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "prompts"
    root.mkdir()
    monkeypatch.setenv("FORGEBENCH_PROMPTS_ROOT", str(root))

    from forgebench.api import (
        PromptCreate,
        PromptLabelUpdate,
        create_prompt_version,
        get_prompt_endpoint,
        list_prompts_endpoint,
        put_prompt_label,
    )

    assert list_prompts_endpoint() == []

    created = create_prompt_version("classify", PromptCreate(body="v1 body", note="seed"))
    assert created["version"] == 1
    assert created["body"] == "v1 body"

    create_prompt_version("classify", PromptCreate(body="v2 body"))
    catalog = list_prompts_endpoint()
    assert len(catalog) == 1
    assert catalog[0]["versions"] == [1, 2]

    latest = get_prompt_endpoint("classify")
    assert latest["body"] == "v2 body"
    assert get_prompt_endpoint("classify", version=1)["body"] == "v1 body"

    labelled = put_prompt_label("classify", PromptLabelUpdate(label="production", version=1))
    assert labelled["labels"] == {"production": 1}
    assert "production" in get_prompt_endpoint("classify", version=1)["labels"]

    # Removing the label (null version) must not touch the version itself.
    removed = put_prompt_label("classify", PromptLabelUpdate(label="production", version=None))
    assert removed["labels"] == {}


def test_prompt_endpoints_report_missing_things_honestly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "prompts"
    root.mkdir()
    monkeypatch.setenv("FORGEBENCH_PROMPTS_ROOT", str(root))

    from forgebench.api import (
        PromptCreate,
        PromptLabelUpdate,
        create_prompt_version,
        get_prompt_endpoint,
        put_prompt_label,
    )

    with pytest.raises(HTTPException) as missing_prompt:
        get_prompt_endpoint("ghost")
    assert missing_prompt.value.status_code == 404

    with pytest.raises(HTTPException) as missing_label_target:
        put_prompt_label("ghost", PromptLabelUpdate(label="production", version=1))
    assert missing_label_target.value.status_code == 404

    create_prompt_version("classify", PromptCreate(body="v1"))
    with pytest.raises(HTTPException) as missing_version:
        get_prompt_endpoint("classify", version=5)
    assert missing_version.value.status_code == 404
