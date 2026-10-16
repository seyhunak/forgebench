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
