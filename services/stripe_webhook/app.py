"""Stripe webhook listener + credit fulfillment for ForgeBench.

One small FastAPI service, managed by devctl (see ``devctl.json`` —
service ``forgebench_stripe``):

- ``POST /stripe/webhook`` — verifies the Stripe signature with the
  standard library (no stripe SDK dependency), resolves the package
  from checkout metadata or the price-id map, and mints a single-use
  voucher code (optionally emailed via SMTP when that env block is set).
- ``POST /redeem {code}`` — consumed by ``forgebench redeem <code>``;
  returns the grant {credits | unlimited, dataset_pack} and burns the
  voucher so a code cannot be used twice.
- ``GET /packages`` / ``GET /health`` — catalog with payment links, and
  liveness.

Configuration (environment):
- ``STRIPE_WEBHOOK_SECRET`` — required for webhook verification; the
  service boots without it (health/packages still work) and the webhook
  endpoint answers 503 loudly instead of guessing.
- ``STRIPE_PRICE_MAP`` — ``price_A=starter_50,price_B=growth_100``
  fallback when checkout metadata is missing.
- ``STRIPE_LEDGER_PATH`` — voucher store (default ``.forgebench/vouchers.json``).
- ``SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD/SMTP_FROM`` — optional
  email fulfillment; without it the voucher lands in the service log.

Metadata scheme — when creating the payment links in Stripe, set
``package`` in the checkout metadata to one of ``starter_50``,
``growth_100``, ``scale_250``, ``max_500``, ``enterprise_unlimited``,
``dataset_pack``. That is the primary resolution path; the price map is
only a safety net.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

try:  # package import and cwd-run both work
    from .catalog import grant_for_package, package_prices
    from .email_help import send_voucher_email
except ImportError:  # running from services/stripe_webhook/
    from catalog import grant_for_package, package_prices  # type: ignore
    from email_help import send_voucher_email  # type: ignore

DEFAULT_LEDGER = Path(".forgebench/vouchers.json")
VOUCHER_PREFIX = "FB"
TOLERANCE_SECONDS = 300  # Stripe-recommended timestamp tolerance

app = FastAPI(title="ForgeBench Stripe Credit Service", version="0.1.0")


def _ledger_path() -> Path:
    return Path(os.environ.get("STRIPE_LEDGER_PATH") or DEFAULT_LEDGER)


def _load_ledger() -> dict[str, Any]:
    path = _ledger_path()
    if not path.exists():
        return {"vouchers": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"vouchers": {}}
    data.setdefault("vouchers", {})
    return data


def _save_ledger(data: dict[str, Any]) -> None:
    path = _ledger_path()
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


def _now() -> int:
    return int(time.time())


def sign_payload(secret: str, timestamp: int, payload: bytes) -> str:
    """The HMAC SHA256 Stripe expects in ``Stripe-Signature`` v1."""
    signed = f"{timestamp}.".encode() + payload
    return hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()


def verify_stripe_signature(
    payload: bytes,
    signature_header: str | None,
    secret: str,
    *,
    tolerance_seconds: int = TOLERANCE_SECONDS,
) -> bool:
    """Verify ``Stripe-Signature`` (t=…,v1=…) with the stdlib only."""
    if not signature_header:
        return False
    parts: dict[str, list[str]] = {}
    for chunk in signature_header.split(","):
        key, _, value = chunk.partition("=")
        parts.setdefault(key.strip(), []).append(value.strip())
    timestamps, sigs = parts.get("t", []), parts.get("v1", [])
    if not timestamps or not sigs:
        return False
    try:
        header_time = int(timestamps[0])
    except ValueError:
        return False
    if abs(_now() - header_time) > tolerance_seconds:
        return False
    expected = sign_payload(secret, header_time, payload)
    return any(hmac.compare_digest(sig, expected) for sig in sigs if sig)


def _new_voucher(package: str) -> str:
    return f"{VOUCHER_PREFIX}-{package.upper()}-{secrets.token_hex(4).upper()}"


def _fetch_line_item_prices(session_id: str) -> list[str]:
    """Price IDs from Stripe, stdlib HTTP, when a secret key is configured."""
    secret_key = os.environ.get("STRIPE_SECRET_KEY")
    if not secret_key or not session_id:
        return []
    import urllib.parse
    import urllib.request

    url = (
        "https://api.stripe.com/v1/checkout/sessions/"
        + urllib.parse.quote(session_id, safe="")
        + "/line_items"
    )
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {secret_key}"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            body = json.loads(response.read().decode("utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [item.get("price", {}).get("id", "") for item in body.get("data", [])]


def _resolve_package(
    event: dict[str, Any],
    line_item_prices: list[str] | None = None,
) -> str | None:
    """Package name from checkout metadata, else via STRIPE_PRICE_MAP."""
    session = event.get("data", {}).get("object", {})
    named = ((session.get("metadata") or {}).get("package") or "").strip()
    if named:
        return named
    price_map: dict[str, str] = {}
    raw = os.environ.get("STRIPE_PRICE_MAP", "")
    for chunk in raw.split(","):
        if "=" in chunk:
            key, value = chunk.split("=", 1)
            price_map[key.strip()] = value.strip()
    for price_id in line_item_prices or []:
        if price_id in price_map:
            return price_map[price_id]
    return None


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request) -> JSONResponse:
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="STRIPE_WEBHOOK_SECRET not set — refusing to accept events.",
        )
    payload = await request.body()
    if not verify_stripe_signature(payload, request.headers.get("Stripe-Signature"), secret):
        raise HTTPException(status_code=400, detail="Bad signature.")
    try:
        event = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Bad payload: {exc}") from exc

    kind = event.get("type", "")
    if kind != "checkout.session.completed":
        return JSONResponse({"handled": False, "type": kind})

    session = event.get("data", {}).get("object", {})
    name = _resolve_package(event, _fetch_line_item_prices(session.get("id", "")))
    grant = grant_for_package(name) if name else None
    if grant is None:
        return JSONResponse(
            {
                "handled": False,
                "type": kind,
                "note": "unknown package — set checkout metadata "
                "'package' or extend STRIPE_PRICE_MAP",
            }
        )

    voucher = _new_voucher(name)
    email = ((session.get("customer_details") or {}).get("email")) or ""
    ledger = _load_ledger()
    ledger["vouchers"][voucher] = {
        "package": name,
        "grant": grant,
        "session_id": session.get("id", ""),
        "customer_email": email,
        "redeemed": False,
        "created_at": _now(),
    }
    _save_ledger(ledger)

    try:
        send_voucher_email(email, voucher, grant)
    except Exception:  # noqa: BLE001 — email is best-effort fulfillment
        print(
            f"[stripe] voucher {voucher} for {name} — SMTP unavailable, "
            "code is in the ledger for manual delivery"
        )

    return JSONResponse({"handled": True, "voucher": voucher})


@app.post("/redeem")
async def redeem_voucher(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Bad JSON: {exc}") from exc
    code = (body or {}).get("code", "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="code is required.")
    ledger = _load_ledger()
    entry = ledger["vouchers"].get(code)
    if entry is None:
        raise HTTPException(status_code=404, detail="Unknown voucher code.")
    if entry.get("redeemed"):
        raise HTTPException(status_code=409, detail="Voucher already redeemed.")
    entry["redeemed"] = True
    _save_ledger(ledger)
    return JSONResponse(entry["grant"])


@app.get("/packages")
async def packages() -> JSONResponse:
    links = {
        key.removeprefix("STRIPE_LINK_").lower(): os.environ[key]
        for key in os.environ
        if key.startswith("STRIPE_LINK_")
    }
    return JSONResponse({"packages": package_prices(), "payment_links": links})


@app.get("/health")
async def health() -> JSONResponse:
    vouchers = _load_ledger()["vouchers"]
    return JSONResponse(
        {
            "ok": True,
            "webhook_configured": bool(os.environ.get("STRIPE_WEBHOOK_SECRET")),
            "vouchers_open": sum(1 for v in vouchers.values() if not v.get("redeemed")),
            "vouchers_redeemed": sum(1 for v in vouchers.values() if v.get("redeemed")),
        }
    )


def main() -> None:
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT") or 8583),
        log_level=os.environ.get("LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
