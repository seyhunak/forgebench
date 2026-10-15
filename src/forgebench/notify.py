"""Post-run webhook notification: one JSON POST to ``FORGEBENCH_WEBHOOK_URL``.

Runs should be able to tell the outside world they finished — a Slack
incomming-webhook URL, a CI listener, or a home-grown collector. The contract
is deliberately tiny: fire once per completed run, never block the run for
more than the connect timeout, never raise. A notification that fails is a
warning in stderr, not a red benchmark.
"""

from __future__ import annotations

import json as _json
import sys
import urllib.request
from collections.abc import Callable
from typing import Any

WEBHOOK_ENV_VAR = "FORGEBENCH_WEBHOOK_URL"
_TIMEOUT_SECONDS = 5.0

SendFn = Callable[[str, bytes, str], Any]

#: Injectable for tests: swaps the actual HTTP send.
_post_urlopen: Callable[..., Any] | None = None


def build_run_payload(manifest: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    """The minimal, comparable summary posted for a finished run."""
    provider = manifest.get("provider", {}) or {}
    dataset = manifest.get("dataset", {}) or {}
    return {
        "event": "forgebench.run.completed",
        "run_id": manifest.get("run_id"),
        "created_at_utc": manifest.get("created_at_utc"),
        "experiment": manifest.get("experiment_name") or manifest.get("task"),
        "dataset": dataset.get("name") or manifest.get("task"),
        "split": dataset.get("split") or manifest.get("split"),
        "provider": provider.get("name"),
        "model": provider.get("model"),
        "n_cases": metrics.get("n_cases"),
        "n_valid": metrics.get("n_valid"),
        "accuracy": metrics.get("accuracy"),
    }


def post_run_webhook(
    manifest: dict[str, Any],
    metrics: dict[str, Any],
    *,
    url: str | None = None,
    send_fn: SendFn | None = None,
) -> bool:
    """POST a run summary to ``FORGEBENCH_WEBHOOK_URL`` (or the explicit url).

    Returns ``True`` when a webhook was configured and delivered, ``False``
    otherwise (unconfigured or failed). Never raises.
    """
    import os

    target = url or os.environ.get(WEBHOOK_ENV_VAR, "").strip()
    if not target:
        return False
    payload = _json.dumps(build_run_payload(manifest, metrics)).encode("utf-8")
    send = send_fn or _default_send
    try:
        send(target, payload, "application/json")
        return True
    except Exception as exc:  # noqa: BLE001 - webhook must never break a run
        print(f"warning: webhook delivery failed: {exc}", file=sys.stderr)
        return False


def _default_send(target: str, payload: bytes, content_type: str) -> None:
    if _post_urlopen is not None:
        _post_urlopen(target, payload, content_type)
        return
    request = urllib.request.Request(
        target,
        data=payload,
        headers={"Content-Type": content_type, "User-Agent": "forgebench-webhook"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS):
        pass


__all__ = ["WEBHOOK_ENV_VAR", "build_run_payload", "post_run_webhook"]
