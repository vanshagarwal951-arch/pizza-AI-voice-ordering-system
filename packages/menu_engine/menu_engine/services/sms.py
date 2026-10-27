"""SMS / WhatsApp order confirmations."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from menu_engine.pricing import format_spoken_amount
from menu_engine.types import CartSummary


def send_order_sms(
    order_id: str,
    summary: CartSummary,
    phone: str | None = None,
) -> dict[str, Any]:
    to = (phone or os.getenv("DEFAULT_NOTIFY_PHONE", "")).strip()
    total = format_spoken_amount(summary.total_cents, summary.currency)
    body = (
        f"DIALOG Pizza: Order #{order_id[:8]} confirmed! "
        f"{summary.item_count} items, {total}. "
        f"Track at dialog.app/orders/{order_id[:8]}"
    )

    sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    from_num = os.getenv("TWILIO_FROM_NUMBER", "").strip()

    if sid and token and from_num and to:
        try:
            return _send_twilio(sid, token, from_num, to, body)
        except Exception as exc:  # noqa: BLE001
            return {"sent": False, "provider": "twilio", "error": str(exc), "body": body}

    log_path = _log_sms(order_id, to or "demo", body)
    return {
        "sent": False,
        "demo_mode": True,
        "provider": "mock",
        "body": body,
        "logged_to": log_path,
        "hint": "Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER for live SMS",
    }


def _send_twilio(sid: str, token: str, from_num: str, to: str, body: str) -> dict[str, Any]:
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    data = urllib.parse.urlencode({"From": from_num, "To": to, "Body": body}).encode()
    import base64

    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header(
        "Authorization",
        "Basic " + base64.b64encode(f"{sid}:{token}".encode()).decode(),
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read().decode())
    return {"sent": True, "provider": "twilio", "message_sid": result.get("sid"), "body": body}


def _log_sms(order_id: str, phone: str, body: str) -> str:
    from menu_engine.db.models import PROJECT_ROOT

    log_dir = PROJECT_ROOT / "data" / "notifications" / "sms"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{order_id}.txt"
    path.write_text(f"To: {phone}\n\n{body}", encoding="utf-8")
    return str(path)
