from __future__ import annotations

import json
import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

from menu_engine.db.models import PROJECT_ROOT
from menu_engine.pricing import format_cents
from menu_engine.types import CartSummary
from menu_engine.utils.console import safe_print


def notify_order_finalized(
    order_id: str,
    session_id: str,
    summary: CartSummary,
    payment: dict | None = None,
) -> dict:
    total = format_cents(summary.total_cents, summary.currency)
    payment_line = ""
    if payment:
        payment_line = f"Payment: {payment.get('method', 'cod')} — {payment.get('status', 'pending')}\n"
    message = (
        f"New order {order_id[:8]}\n"
        f"Session: {session_id}\n"
        f"Items: {summary.item_count}\n"
        f"Total: {total}\n"
        f"{payment_line}\n"
        f"{summary.spoken_summary}"
    )

    log_dir = PROJECT_ROOT / "data" / "notifications"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{order_id}.txt"
    log_file.write_text(message, encoding="utf-8")

    result = {"logged_to": str(log_file), "email_sent": False, "sms_sent": False}

    smtp_host = __import__("os").getenv("SMTP_HOST")
    smtp_to = __import__("os").getenv("NOTIFY_EMAIL")
    if smtp_host and smtp_to:
        try:
            _send_email(smtp_host, smtp_to, f"New DIALOG Pizza Order {order_id[:8]}", message)
            result["email_sent"] = True
        except Exception as exc:  # noqa: BLE001
            result["email_error"] = str(exc)

    safe_print(f"\n{'=' * 50}\nKITCHEN NOTIFICATION\n{message}\n{'=' * 50}\n")
    return result


def _send_email(host: str, to_addr: str, subject: str, body: str) -> None:
    import os

    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = user or "voice-ordering@localhost"
    msg["To"] = to_addr
    with smtplib.SMTP(host, port) as server:
        server.starttls()
        if user and password:
            server.login(user, password)
        server.send_message(msg)
