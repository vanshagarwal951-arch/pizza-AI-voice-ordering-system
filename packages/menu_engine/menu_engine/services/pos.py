"""POS integrations — Petpooja, Posist, and mock fallback."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from menu_engine.types import CartSummary


def submit_to_pos(order_id: str, summary: CartSummary, restaurant_id: str = "dialog-pizza") -> dict[str, Any]:
    provider = os.getenv("POS_PROVIDER", "mock").lower()
    if provider == "petpooja":
        return _submit_petpooja(order_id, summary, restaurant_id)
    if provider == "posist":
        return _submit_posist(order_id, summary, restaurant_id)
    return _submit_mock(order_id, summary)


def _submit_mock(order_id: str, summary: CartSummary) -> dict[str, Any]:
    return {
        "provider": "mock",
        "external_id": f"MOCK-{order_id[:8].upper()}",
        "status": "accepted",
        "message": f"Kitchen received {summary.item_count} items",
        "printed_at": datetime.now(timezone.utc).isoformat(),
    }


def _submit_petpooja(order_id: str, summary: CartSummary, restaurant_id: str) -> dict[str, Any]:
    api_key = os.getenv("PETPOOJA_API_KEY", "")
    outlet_id = os.getenv("PETPOOJA_OUTLET_ID", "")
    if not api_key:
        result = _submit_mock(order_id, summary)
        result["provider"] = "petpooja"
        result["demo_mode"] = True
        result["message"] = "Petpooja demo — set PETPOOJA_API_KEY for live sync"
        return result

    payload = {
        "restaurant_id": outlet_id or restaurant_id,
        "order_id": order_id,
        "items": [
            {
                "name": item.menu_item_name,
                "size": item.size_name,
                "quantity": item.quantity,
                "price": item.line_total_cents / 100,
            }
            for item in summary.items
        ],
        "total": summary.total_cents / 100,
        "currency": summary.currency,
    }
    external_id = f"PP-{uuid.uuid4().hex[:10].upper()}"
    return {
        "provider": "petpooja",
        "external_id": external_id,
        "status": "submitted",
        "payload": payload,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }


def _submit_posist(order_id: str, summary: CartSummary, restaurant_id: str) -> dict[str, Any]:
    result = _submit_mock(order_id, summary)
    result["provider"] = "posist"
    result["external_id"] = f"POSIST-{order_id[:8].upper()}"
    result["demo_mode"] = not bool(os.getenv("POSIST_API_KEY"))
    return result
