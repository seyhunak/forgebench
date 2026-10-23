"""Local credit ledger for the Stripe package model.

Business model: 1 credit = $0.10, one benchmark or task run = 1 credit.
Credits arrive as voucher codes issued by the Stripe webhook service
(``services/stripe_webhook``) and are redeemed once (
``forgebench redeem FB-...``); the redeemed balance lives locally so the
harness runs offline afterwards without a license server.

The ledger is a small JSON file (default ``.forgebench/credits.json``,
override with ``FORGEBENCH_CREDITS_PATH``). It is git-ignored — never
committed — and written atomically on every mutation.

Modes (``FORGEBENCH_CREDITS_MODE``):
- ``off``      (default, MVP): nothing happens; runs work as always.
- ``observe``: every run is recorded locally, nothing is blocked.
- ``enforce``: a run with an empty balance is refused before inference.
"""

from __future__ import annotations

import json
import os
import tempfile
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_LEDGER = Path(".forgebench/credits.json")
MAX_USAGE_ROWS = 500  # tail of usage history kept on disk


class CreditsError(Exception):
    """Raised when a run cannot start under credit enforcement."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def ledger_path() -> Path:
    raw = os.environ.get("FORGEBENCH_CREDITS_PATH")
    return Path(raw) if raw else DEFAULT_LEDGER


def mode() -> str:
    return (os.environ.get("FORGEBENCH_CREDITS_MODE") or "off").strip().lower()


def run_credit_id(identifier: str) -> str:
    """A stable-enough identity for a credit usage row (name + minute stamp)."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = str(identifier or "").strip() or "run"
    return f"{base}-{stamp}"


def load(path: Path | None = None) -> dict[str, Any]:
    path = path or ledger_path()
    if not path.exists():
        return {"balance": 0, "unlimited": False, "grants": [], "usage": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"balance": 0, "unlimited": False, "grants": [], "usage": []}
    data.setdefault("balance", 0)
    data.setdefault("unlimited", False)
    data.setdefault("grants", [])
    data.setdefault("usage", [])
    return data


def _save(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    )
    try:
        with handle as fp:
            json.dump(data, fp, indent=2, sort_keys=True)
            fp.write("\n")
        Path(handle.name).replace(path)
    finally:
        Path(handle.name).unlink(missing_ok=True)


def status(path: Path | None = None) -> dict[str, Any]:
    data = load(path)
    return {
        "mode": mode(),
        "balance": data["balance"],
        "unlimited": data["unlimited"],
        "grants": data["grants"],
        "usage": data["usage"],
        "ledger": str(path or ledger_path()),
    }


def consume_run(
    run_kind: str,
    run_id: str,
    *,
    amount: int = 1,
    path: Path | None = None,
) -> dict[str, Any] | None:
    """Record one run against the ledger; refuse it when enforcing without funds.

    Called at the top of ``run_experiment`` / ``run_task_experiment``. In
    ``off`` mode this is a no-op so community use is untouched. Note the
    MVP semantics: credits are counted per *run*, offline/community runs
    obviously still work while ``off``.
    """
    current = mode()
    if current == "off":
        return None
    path = path or ledger_path()
    data = load(path)
    if not data["unlimited"] and current == "enforce" and data["balance"] < amount:
        raise CreditsError(
            f"No credits left on this machine "
            f"(balance {data['balance']}, this run needs {amount}). "
            "Buy a pack and redeem it with: forgebench redeem <code> "
            "(see the Stripe service in services/stripe_webhook)."
        )
    if not data["unlimited"]:
        data["balance"] = max(0, data["balance"] - amount)
    data["usage"].append({"at": _now(), "kind": run_kind, "run": run_id, "credits": amount})
    data["usage"] = data["usage"][-MAX_USAGE_ROWS:]
    _save(data, path)
    return {"balance": data["balance"], "unlimited": data["unlimited"]}


def apply_grant(
    grant: dict[str, Any],
    *,
    path: Path | None = None,
) -> dict[str, Any]:
    """Merge a redeemed voucher grant into the local ledger."""
    path = path or ledger_path()
    data = load(path)
    credits = int(grant.get("credits", 0) or 0)
    unlimited = bool(grant.get("unlimited", False))
    data["grants"].append(
        {
            "code": grant.get("voucher", ""),
            "package": grant.get("package", ""),
            "label": grant.get("label", ""),
            "credits": credits,
            "unlimited": unlimited,
            "at": _now(),
        }
    )
    data["unlimited"] = data["unlimited"] or unlimited
    if not data["unlimited"]:
        data["balance"] += credits
    _save(data, path)
    return {"balance": data["balance"], "unlimited": data["unlimited"]}


def redeem(
    code: str,
    *,
    service_url: str | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """Redeem a voucher code against the Stripe webhook service.

    Default service: ``FORGEBENCH_CREDITS_SERVICE`` or
    ``http://127.0.0.1:8583`` (the devctl-managed listener).
    """
    host = (
        service_url or os.environ.get("FORGEBENCH_CREDITS_SERVICE") or "http://127.0.0.1:8583"
    ).rstrip("/")
    payload = json.dumps({"code": code.strip()}).encode("utf-8")
    request = urllib.request.Request(
        f"{host}/redeem",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": f"forgebench-credits/{_version()}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
        body = json.loads(response.read().decode("utf-8"))
    grant = {"voucher": code.strip(), **body}
    state = apply_grant(grant, path=path)
    state["package"] = body.get("package", "")
    return state


def _version() -> str:  # local import guard: avoid cycle with __init__
    from . import __version__

    return __version__
