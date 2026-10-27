"""Business analytics from orders and call logs."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any


def compute_analytics(orders: list[dict], calls: list[dict]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)

    today_orders = []
    week_orders = []
    for o in orders:
        created = datetime.fromisoformat(o["created_at"])
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if created >= today_start:
            today_orders.append(o)
        if created >= week_start:
            week_orders.append(o)

    revenue_today = sum(o["total_cents"] for o in today_orders)
    revenue_week = sum(o["total_cents"] for o in week_orders)
    aov = revenue_week // len(week_orders) if week_orders else 0

    hourly: dict[int, int] = defaultdict(int)
    for o in week_orders:
        h = datetime.fromisoformat(o["created_at"]).hour
        hourly[h] += 1

    peak_hour = max(hourly, key=hourly.get) if hourly else 12

    finalized = len([c for c in calls if c.get("status") == "ended"])
    active_calls = len([c for c in calls if c.get("status") == "active"])

    return {
        "orders_today": len(today_orders),
        "orders_week": len(week_orders),
        "revenue_today_cents": revenue_today,
        "revenue_week_cents": revenue_week,
        "average_order_value_cents": aov,
        "total_orders": len(orders),
        "calls_total": len(calls),
        "calls_completed": finalized,
        "calls_active": active_calls,
        "conversion_rate": round(len(week_orders) / max(finalized, 1) * 100, 1),
        "peak_hour": peak_hour,
        "hourly_orders": dict(sorted(hourly.items())),
        "currency": orders[0]["currency"] if orders else "INR",
    }
