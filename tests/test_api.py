"""API route wiring: exercised without starting an HTTP server.

The FastAPI app is an optional (``[ui]``) dependency, so these tests skip when
it is not installed rather than failing a plain ``[dev]`` environment.
"""

from __future__ import annotations

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
    """Ollama: key storage on Setup (hint shown), not a runnable adapter."""
    from forgebench.api import list_env, list_providers

    ollama = next(p for p in list_env()["providers"] if p["provider"] == "ollama")
    assert ollama["key_var"] == "OLLAMA_API_KEY"
    assert ollama["model_var"] == "OLLAMA_MODEL"
    assert "key optional" in ollama["hint"]

    # The API key view offers runnable adapters only — no ollama.
    assert "ollama" not in [p["id"] for p in list_providers()]


def test_setup_never_offers_the_mock_provider() -> None:
    """Mock needs no key, so it must not take up a row on Setup."""
    from forgebench.api import list_env

    assert "mock" not in [p["provider"] for p in list_env()["providers"]]
