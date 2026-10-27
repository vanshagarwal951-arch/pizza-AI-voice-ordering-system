from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from menu_engine.db.models import PROJECT_ROOT
from menu_engine.types import CartSummary
from menu_engine.utils.file_ops import atomic_write_json


def write_kitchen_ticket(order_id: str, session_id: str, summary: CartSummary) -> dict:
    tickets_dir = PROJECT_ROOT / "data" / "tickets"
    tickets_dir.mkdir(parents=True, exist_ok=True)

    ticket = {
        "ticket_id": str(uuid.uuid4()),
        "order_id": order_id,
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "item_count": summary.item_count,
        "total_cents": summary.total_cents,
        "currency": summary.currency,
        "items": [
            {
                "name": item.menu_item_name,
                "size": item.size_name,
                "half_and_half": item.is_half_and_half,
                "left": [{"id": t.modifier_id, "extra": t.extra} for t in item.left_toppings],
                "right": [{"id": t.modifier_id, "extra": t.extra} for t in item.right_toppings],
                "whole": [{"id": t.modifier_id, "extra": t.extra} for t in item.whole_toppings],
                "quantity": item.quantity,
                "line_total_cents": item.line_total_cents,
            }
            for item in summary.items
        ],
        "spoken_summary": summary.spoken_summary,
        "status": "queued",
    }

    file_path = tickets_dir / f"{order_id}.json"
    atomic_write_json(file_path, ticket)
    ticket["file_path"] = str(file_path)
    return ticket


def submit_to_mock_pos(order_id: str, summary: CartSummary) -> dict:
    return {
        "provider": "mock",
        "external_id": f"MOCK-{order_id[:8].upper()}",
        "status": "accepted",
        "message": f"Kitchen received {summary.item_count} items",
        "printed_at": datetime.now(timezone.utc).isoformat(),
    }
