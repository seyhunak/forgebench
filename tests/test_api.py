"""API route wiring: exercised without starting an HTTP server.

The FastAPI app is an optional (``[ui]``) dependency, so these tests skip when
it is not installed rather than failing a plain ``[dev]`` environment.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi import HTTPException  # noqa: E402

from forgebench.api import app, validate_task_endpoint  # noqa: E402


def _paths() -> list[str]:
    return [getattr(route, "path", "") for route in app.routes]


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
