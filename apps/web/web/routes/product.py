"""Product APIs — payments, KDS, admin, analytics, auth."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field, validator

from menu_engine.db.models import PROJECT_ROOT
from menu_engine.services.analytics import compute_analytics
from menu_engine.services.auth import login, verify_token, verify_token_bool
from menu_engine.services.inventory import (
    get_inventory_status,
    toggle_item_availability,
    toggle_modifier_86,
)
from menu_engine.services.menu_admin import update_item_price, update_restaurant_settings
from menu_engine.services.payments import create_payment, mark_payment_paid
from menu_engine.menu.loader import load_menu, reset_menu_cache

router = APIRouter(prefix="/api", tags=["product"])


class LoginRequest(BaseModel):
    username: str = Field(default="admin", max_length=50)
    password: str = Field(default="", max_length=200)

    @validator("username")
    def validate_username(cls, v):
        """Validate username is not empty."""
        if not v or not v.strip():
            raise ValueError("username cannot be empty")
        return v.strip()


class PaymentRequest(BaseModel):
    order_id: str = Field(max_length=100)
    amount_cents: int = Field(gt=0, le=10000000)  # Max ₹100,000
    currency: str = Field(default="INR", max_length=3)
    method: str = Field(default="cod", max_length=20)
    customer_phone: str | None = Field(default=None, max_length=20)

    @validator("currency")
    def validate_currency(cls, v):
        """Validate currency code."""
        allowed = {"INR", "USD", "EUR"}
        if v.upper() not in allowed:
            raise ValueError(f"Currency must be one of {allowed}")
        return v.upper()

    @validator("method")
    def validate_method(cls, v):
        """Validate payment method."""
        allowed = {"cod", "upi", "card", "cash"}
        if v.lower() not in allowed:
            raise ValueError(f"Method must be one of {allowed}")
        return v.lower()


class KitchenStatusRequest(BaseModel):
    status: str = Field(max_length=20)

    @validator("status")
    def validate_status(cls, v):
        """Validate kitchen ticket status."""
        allowed = {"queued", "preparing", "ready", "served", "cancelled"}
        if v.lower() not in allowed:
            raise ValueError(f"Status must be one of {allowed}")
        return v.lower()


class ItemAvailabilityRequest(BaseModel):
    available: bool


class Modifier86Request(BaseModel):
    is_86d: bool


class PriceUpdateRequest(BaseModel):
    item_id: str = Field(max_length=100)
    size_id: str = Field(max_length=50)
    price_cents: int = Field(gt=0, le=10000000)  # Max ₹100,000


class RestaurantSettingsRequest(BaseModel):
    settings: dict[str, Any]


def _require_admin(authorization: str | None = Header(default=None)) -> dict[str, str]:
    """Require admin authentication. Returns user info dict."""
    token = (authorization or "").replace("Bearer ", "").strip()
    user_info = verify_token(token)
    if not user_info or user_info.get("role") != "admin":
        raise HTTPException(401, "Admin authentication required")
    return user_info


def _require_staff(authorization: str | None = Header(default=None)) -> dict[str, str]:
    """Require staff or admin authentication. Returns user info dict."""
    token = (authorization or "").replace("Bearer ", "").strip()
    user_info = verify_token(token)
    if not user_info or user_info.get("role") not in ("admin", "staff"):
        raise HTTPException(401, "Staff authentication required")
    return user_info


def _get_client_ip(request) -> str:
    """Extract client IP for rate limiting."""
    # Check X-Forwarded-For header first (if behind proxy)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    # Fall back to direct connection
    if hasattr(request.client, "host"):
        return request.client.host
    return "unknown"


def _get_repo():
    from menu_engine import get_cart_repository

    return get_cart_repository()


@router.post("/auth/login")
def auth_login(req: LoginRequest, request: Request):
    client_ip = _get_client_ip(request)
    result = login(req.username, req.password, client_ip)
    if not result:
        raise HTTPException(401, "Invalid credentials")
    return result


@router.get("/restaurants")
def list_restaurants():
    path = PROJECT_ROOT / "data" / "restaurants.json"
    if not path.exists():
        menu = load_menu()
        return {"restaurants": [menu["restaurant"]]}
    return {"restaurants": json.loads(path.read_text(encoding="utf-8"))}


@router.get("/analytics")
def analytics_summary(authorization: str | None = Header(default=None)):
    _require_staff(authorization)
    repo = _get_repo()
    orders = repo.list_orders(limit=500)
    calls = repo.list_call_logs(limit=500)
    return compute_analytics(orders, calls)


@router.get("/kds/tickets")
def kds_tickets(status: str | None = None, authorization: str | None = Header(default=None)):
    _require_staff(authorization)
    return {"tickets": _get_repo().list_kitchen_tickets(status=status)}


@router.patch("/kds/tickets/{ticket_id}")
def kds_update(ticket_id: str, req: KitchenStatusRequest, authorization: str | None = Header(default=None)):
    _require_staff(authorization)
    try:
        return _get_repo().update_kitchen_ticket(ticket_id, req.status)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/pos/submissions")
def pos_submissions(authorization: str | None = Header(default=None)):
    _require_staff(authorization)
    return {"submissions": _get_repo().list_pos_submissions()}


@router.post("/payments/create")
def payment_create(req: PaymentRequest, authorization: str | None = Header(default=None)):
    _require_staff(authorization)
    return create_payment(
        req.order_id, req.amount_cents, req.currency, req.method, req.customer_phone
    )


@router.post("/payments/{payment_id}/confirm")
def payment_confirm(payment_id: str, authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    try:
        updated = _get_repo().update_payment_status(payment_id, "paid")
        return mark_payment_paid(updated)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/inventory")
def inventory_list(authorization: str | None = Header(default=None)):
    _require_staff(authorization)
    return get_inventory_status()


@router.patch("/inventory/items/{item_id}")
def inventory_item(item_id: str, req: ItemAvailabilityRequest, authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    try:
        reset_menu_cache()
        return toggle_item_availability(item_id, req.available)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.patch("/inventory/modifiers/{modifier_id}")
def inventory_modifier(
    modifier_id: str, req: Modifier86Request, authorization: str | None = Header(default=None)
):
    _require_admin(authorization)
    try:
        return toggle_modifier_86(modifier_id, req.is_86d)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.patch("/admin/menu/price")
def admin_price(req: PriceUpdateRequest, authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    try:
        return update_item_price(req.item_id, req.size_id, req.price_cents)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.patch("/admin/restaurant")
def admin_restaurant(req: RestaurantSettingsRequest, authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    return update_restaurant_settings(req.settings)


@router.get("/platform/status")
def platform_status():
    import os

    menu = load_menu()
    return {
        "product": "DIALOG Voice Ordering Platform",
        "version": "2.0.0",
        "features": {
            "voice_ordering": bool(os.getenv("LIVEKIT_URL")),
            "payments": True,
            "pos_integration": os.getenv("POS_PROVIDER", "mock"),
            "sms": bool(os.getenv("TWILIO_ACCOUNT_SID")),
            "multi_restaurant": True,
            "kds": True,
            "analytics": True,
            "inventory": True,
            "menu_admin": True,
            "auth": True,
        },
        "restaurant": menu["restaurant"],
        "menu_items": len(menu["items"]),
    }
