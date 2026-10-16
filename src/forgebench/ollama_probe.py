"""Is Ollama installed, running, and which models does it have locally?

The dashboard's key view calls this when the user picks Ollama as the
provider: models.dev has no Ollama catalog — its models are whatever the
user has pulled — so the honest model list comes from the daemon itself,
and the user is told plainly whether Ollama is installed at all.

Everything here is best-effort and never raises: a missing binary, a
stopped daemon, or an unreadable response degrades to ``running: false``
with an explanatory ``detail``, never an error.
"""

from __future__ import annotations

import json
import os
import shutil
import urllib.request

#: Default local daemon address. ``OLLAMA_HOST`` overrides it (``host:port``
#: or a full URL, matching how the Ollama CLI reads the variable).
_DEFAULT_HOST = "http://127.0.0.1:11434"


def ollama_host() -> str:
    """Normalized daemon base URL, without a trailing slash."""
    raw = (os.environ.get("OLLAMA_HOST") or "").strip() or _DEFAULT_HOST
    if not raw.startswith(("http://", "https://")):
        raw = f"http://{raw}"
    return raw.rstrip("/")


def ollama_status(timeout: float = 1.5) -> dict:
    """Probe the binary and the daemon; list local models when reachable.

    Returns ``binary`` (path or None), ``installed``, ``running``, ``host``,
    ``models`` (daemon order, names as Ollama reports them) and ``detail``.
    A running daemon counts as installed even when the binary is not on
    ``PATH`` (the macOS app keeps it inside the bundle).
    """
    binary = shutil.which("ollama")
    host = ollama_host()
    status: dict = {
        "binary": binary,
        "installed": bool(binary),
        "running": False,
        "host": host,
        "models": [],
        "capabilities": {},
        "detail": "",
    }

    error: str | None = None
    payload: object | None = None
    try:
        request = urllib.request.Request(f"{host}/api/tags", method="GET")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - a probe failure *is* the answer
        error = f"{type(exc).__name__}: {exc}"

    if isinstance(payload, dict):
        names = [
            str(model.get("name") or model.get("model") or "").strip()
            for model in payload.get("models") or []
        ]
        status["running"] = True
        status["installed"] = True  # a running daemon is an installed Ollama
        status["models"] = [name for name in names if name]
        status["capabilities"] = {
            str(model.get("name") or model.get("model") or "").strip(): list(
                model.get("capabilities") or []
            )
            for model in payload.get("models") or []
            if str(model.get("name") or model.get("model") or "").strip()
        }
        status["detail"] = f"daemon answering on {host}"
    elif binary:
        status["detail"] = f"binary at {binary} but daemon not answering on {host} ({error})"
    else:
        status["detail"] = f"no binary on PATH and no daemon at {host} ({error})"
    return status
