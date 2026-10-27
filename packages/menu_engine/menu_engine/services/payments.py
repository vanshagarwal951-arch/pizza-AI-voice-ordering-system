"""Payment processing — Razorpay, UPI, and Cash on Delivery."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from menu_engine.pricing import format_spoken_amount


def create_payment(
    order_id: str,
    amount_cents: int,
    currency: str,
    method: str = "cod",
    customer_phone: str | None = None,
) -> dict[str, Any]:
    """Create a payment record. Uses Razorpay when configured, else mock/demo mode."""
    payment_id = str(uuid.uuid4())
    spoken = format_spoken_amount(amount_cents, currency)

    if method == "cod":
        return {
            "id": payment_id,
            "order_id": order_id,
            "method": "cod",
            "status": "pending_collection",
            "amount_cents": amount_cents,
            "currency": currency,
            "spoken_amount": spoken,
            "message": f"Cash on delivery — collect {spoken} at doorstep.",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    if method == "upi":
        upi_id = os.getenv("UPI_VPA", "dialogpizza@upi")
        return {
            "id": payment_id,
            "order_id": order_id,
            "method": "upi",
            "status": "awaiting_payment",
            "amount_cents": amount_cents,
            "currency": currency,
            "spoken_amount": spoken,
            "upi_link": f"upi://pay?pa={upi_id}&pn=DIALOG+Pizza&am={amount_cents / 100:.2f}&cu=INR",
            "upi_id": upi_id,
            "message": f"Pay {spoken} via UPI to {upi_id}",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    if method == "razorpay":
        key_id = os.getenv("RAZORPAY_KEY_ID", "").strip()
        if key_id:
            return _create_razorpay_order(payment_id, order_id, amount_cents, currency, key_id)
        return _create_mock_razorpay(payment_id, order_id, amount_cents, currency)

    return {
        "id": payment_id,
        "order_id": order_id,
        "method": method,
        "status": "failed",
        "error": f"Unknown payment method: {method}",
    }


def _create_mock_razorpay(
    payment_id: str, order_id: str, amount_cents: int, currency: str
) -> dict[str, Any]:
    spoken = format_spoken_amount(amount_cents, currency)
    external_id = f"order_{order_id[:8]}"
    return {
        "id": payment_id,
        "order_id": order_id,
        "method": "razorpay",
        "status": "created",
        "amount_cents": amount_cents,
        "currency": currency,
        "spoken_amount": spoken,
        "razorpay_order_id": external_id,
        "checkout_url": f"/checkout?order={order_id}&demo=1",
        "demo_mode": True,
        "message": f"Demo checkout — {spoken}. Configure RAZORPAY_KEY_ID for live payments.",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _create_razorpay_order(
    payment_id: str, order_id: str, amount_cents: int, currency: str, key_id: str
) -> dict[str, Any]:
    import urllib.error
    import urllib.request

    secret = os.getenv("RAZORPAY_KEY_SECRET", "")
    payload = json.dumps(
        {
            "amount": amount_cents,
            "currency": currency,
            "receipt": order_id[:40],
            "notes": {"order_id": order_id},
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.razorpay.com/v1/orders",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    import base64

    creds = base64.b64encode(f"{key_id}:{secret}".encode()).decode()
    req.add_header("Authorization", f"Basic {creds}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        return {
            "id": payment_id,
            "order_id": order_id,
            "method": "razorpay",
            "status": "created",
            "amount_cents": amount_cents,
            "currency": currency,
            "razorpay_order_id": data["id"],
            "razorpay_key_id": key_id,
            "demo_mode": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    except (urllib.error.URLError, KeyError, json.JSONDecodeError) as exc:
        return _create_mock_razorpay(payment_id, order_id, amount_cents, currency) | {
            "razorpay_error": str(exc),
        }


def mark_payment_paid(payment: dict[str, Any]) -> dict[str, Any]:
    payment = dict(payment)
    payment["status"] = "paid"
    payment["paid_at"] = datetime.now(timezone.utc).isoformat()
    return payment
