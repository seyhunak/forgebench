"""Optional SMTP fulfillment for Stripe vouchers.

Uncle Bob's rule: the webhook must never fail because email does.
``send_voucher_email`` returns quietly when SMTP is not configured, and
the webhook falls back to logging the code for manual delivery. When
SMTP_* is configured the voucher becomes a real email.
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Any


def smtp_configured() -> bool:
    return bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_FROM"))


def send_voucher_email(to: str, code: str, grant: dict[str, Any]) -> bool:
    """Best-effort email; safe no-op when SMTP or recipient is missing."""
    if not to or not smtp_configured():
        return False
    msg = EmailMessage()
    msg["Subject"] = f"Your ForgeBench credits: {grant.get('label', 'package')}"
    msg["From"] = os.environ["SMTP_FROM"]
    msg["To"] = to
    credits = str(grant.get("credits", ""))
    if grant.get("unlimited"):
        credits = "unlimited"
    msg.set_content(
        "Thank you for your purchase.\n\n"
        f"Package: {grant.get('label')} ({credits} credits)\n\n"
        f"Redeem inside ForgeBench:\n\n"
        f"    forgebench redeem {code}\n\n"
        "Each benchmark or task run uses 1 credit ($0.10). The balance "
        "lives on your machine in .forgebench/credits.json.\n"
    )
    with smtplib.SMTP(
        os.environ["SMTP_HOST"],
        int(os.environ.get("SMTP_PORT") or 587),
        timeout=15,
    ) as conn:
        if os.environ.get("SMTP_USER"):
            conn.starttls()
            conn.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
        conn.send_message(msg)
    return True
