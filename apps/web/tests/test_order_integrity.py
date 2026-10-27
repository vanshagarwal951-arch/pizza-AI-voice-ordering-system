"""Tests for web order processing, database health, and session cleanup APIs."""

from __future__ import annotations

import os
import uuid
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

os.environ["ADMIN_USERNAME"] = "test_admin"
os.environ["ADMIN_PASSWORD"] = "test_secure_password_123"
os.environ["AUTH_SECRET"] = "test_secret_key_for_hmac_signing_xyz"

from web.main import app
from menu_engine.services.auth import _reset_rate_limit

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_rate_limiting():
    _reset_rate_limit()
    yield
    _reset_rate_limit()


@pytest.fixture
def staff_token():
    res = client.post(
        "/api/auth/login",
        json={"username": "test_admin", "password": "test_secure_password_123"},
    )
    assert res.status_code == 200
    return res.json()["token"]


def test_health_check_reports_database_status():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"


def test_health_check_reports_degraded_when_database_fails():
    with patch("web.main.ping_database", return_value=False):
        res = client.get("/api/health")
        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "degraded"
        assert data["database"] == "unreachable"


def test_cleanup_sessions_requires_staff_auth():
    # Unauthenticated
    res_no_auth = client.post("/api/sessions/cleanup", json={"max_age_hours": 24.0})
    assert res_no_auth.status_code == 401


def test_cleanup_sessions_with_staff_auth(staff_token):
    res = client.post(
        "/api/sessions/cleanup",
        json={"max_age_hours": 12.0},
        headers={"Authorization": f"Bearer {staff_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "cleaned_sessions" in data
    assert data["max_age_hours"] == 12.0


def test_tool_invoke_handles_idempotent_finalization():
    session_id = f"web-idempotent-{uuid.uuid4().hex[:8]}"
    client.post(f"/api/sessions/{session_id}/start")

    # Add item
    add_res = client.post(
        "/api/tools/invoke",
        json={
            "session_id": session_id,
            "tool": "add_item",
            "args": {"item_name": "margherita", "size": "medium"},
        },
    )
    assert add_res.status_code == 200
    assert add_res.json()["success"] is True

    # Finalize with idempotency key
    key = f"web-test-key-{uuid.uuid4().hex[:8]}"
    fin_1 = client.post(
        "/api/tools/invoke",
        json={
            "session_id": session_id,
            "tool": "finalize_order",
            "args": {
                "confirmed": True,
                "payment_method": "cod",
                "idempotency_key": key,
            },
        },
    )
    assert fin_1.status_code == 200
    assert fin_1.json()["success"] is True
    msg_1 = fin_1.json()["message"]

    # Replay with same key and same payload
    fin_2 = client.post(
        "/api/tools/invoke",
        json={
            "session_id": session_id,
            "tool": "finalize_order",
            "args": {
                "confirmed": True,
                "payment_method": "cod",
                "idempotency_key": key,
            },
        },
    )
    assert fin_2.status_code == 200
    assert fin_2.json()["success"] is True
    assert fin_2.json()["message"] == msg_1
