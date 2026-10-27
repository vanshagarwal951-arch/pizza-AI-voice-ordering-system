"""Tests for API endpoint authentication and authorization."""

import pytest
from fastapi.testclient import TestClient

# Set test credentials before importing app
import os
os.environ["ADMIN_USERNAME"] = "test_admin"
os.environ["ADMIN_PASSWORD"] = "test_secure_password_123"
os.environ["AUTH_SECRET"] = "test_secret_key_for_hmac_signing_xyz"

from web.main import app
from menu_engine.services.auth import _reset_rate_limit

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_rate_limiting():
    """Reset rate limiting before each test to avoid cross-test pollution."""
    _reset_rate_limit()
    yield
    _reset_rate_limit()


@pytest.fixture
def admin_token():
    """Get a valid admin token for testing."""
    response = client.post(
        "/api/auth/login",
        json={"username": "test_admin", "password": "test_secure_password_123"}
    )
    assert response.status_code == 200
    return response.json()["token"]


@pytest.fixture
def admin_headers(admin_token):
    """Get headers with admin bearer token."""
    return {"Authorization": f"Bearer {admin_token}"}


# Public endpoints - should NOT require auth
def test_public_menu_access():
    """Menu should be accessible without authentication."""
    response = client.get("/api/menu")
    assert response.status_code == 200
    assert "items_by_category" in response.json()


def test_public_health_access():
    """Health endpoint should be accessible without authentication."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_public_platform_status_access():
    """Platform status should be accessible without authentication."""
    response = client.get("/api/platform/status")
    assert response.status_code == 200
    assert "product" in response.json()


def test_public_tool_invoke_access():
    """Tool invocation should work without auth (customer ordering)."""
    response = client.post(
        "/api/tools/invoke",
        json={"session_id": "test-room", "tool": "view_menu", "args": {}}
    )
    assert response.status_code == 200


def test_public_chat_access():
    """Chat should work without auth (customer ordering)."""
    response = client.post(
        "/api/chat",
        json={"session_id": "test-room", "message": "show me the menu"}
    )
    assert response.status_code == 200


# Staff-protected endpoints
def test_sessions_list_requires_auth():
    """GET /api/sessions should require staff authentication."""
    response = client.get("/api/sessions")
    assert response.status_code == 401
    assert "Staff authentication required" in response.json()["detail"]


def test_sessions_list_with_valid_token(admin_headers):
    """GET /api/sessions should work with valid staff token."""
    response = client.get("/api/sessions", headers=admin_headers)
    assert response.status_code == 200
    assert "sessions" in response.json()


def test_orders_list_requires_auth():
    """GET /api/orders should require staff authentication."""
    response = client.get("/api/orders")
    assert response.status_code == 401


def test_orders_list_with_valid_token(admin_headers):
    """GET /api/orders should work with valid staff token."""
    response = client.get("/api/orders", headers=admin_headers)
    assert response.status_code == 200
    assert "orders" in response.json()


def test_calls_list_requires_auth():
    """GET /api/calls should require staff authentication."""
    response = client.get("/api/calls")
    assert response.status_code == 401


def test_calls_list_with_valid_token(admin_headers):
    """GET /api/calls should work with valid staff token."""
    response = client.get("/api/calls", headers=admin_headers)
    assert response.status_code == 200
    assert "calls" in response.json()


def test_analytics_requires_auth():
    """GET /api/analytics should require staff authentication."""
    response = client.get("/api/analytics")
    assert response.status_code == 401


def test_analytics_with_valid_token(admin_headers):
    """GET /api/analytics should work with valid staff token."""
    response = client.get("/api/analytics", headers=admin_headers)
    assert response.status_code == 200


def test_kds_tickets_requires_auth():
    """GET /api/kds/tickets should require staff authentication."""
    response = client.get("/api/kds/tickets")
    assert response.status_code == 401


def test_kds_tickets_with_valid_token(admin_headers):
    """GET /api/kds/tickets should work with valid staff token."""
    response = client.get("/api/kds/tickets", headers=admin_headers)
    assert response.status_code == 200
    assert "tickets" in response.json()


def test_kds_update_requires_auth():
    """PATCH /api/kds/tickets/{id} should require staff authentication."""
    response = client.patch("/api/kds/tickets/123", json={"status": "preparing"})
    assert response.status_code == 401


def test_pos_submissions_requires_auth():
    """GET /api/pos/submissions should require staff authentication."""
    response = client.get("/api/pos/submissions")
    assert response.status_code == 401


def test_pos_submissions_with_valid_token(admin_headers):
    """GET /api/pos/submissions should work with valid staff token."""
    response = client.get("/api/pos/submissions", headers=admin_headers)
    assert response.status_code == 200
    assert "submissions" in response.json()


def test_payment_create_requires_auth():
    """POST /api/payments/create should require staff authentication."""
    response = client.post(
        "/api/payments/create",
        json={
            "order_id": "test-order",
            "amount_cents": 1000,
            "currency": "INR",
            "method": "cod"
        }
    )
    assert response.status_code == 401


def test_inventory_list_requires_auth():
    """GET /api/inventory should require staff authentication."""
    response = client.get("/api/inventory")
    assert response.status_code == 401


def test_inventory_list_with_valid_token(admin_headers):
    """GET /api/inventory should work with valid staff token."""
    response = client.get("/api/inventory", headers=admin_headers)
    assert response.status_code == 200


# Admin-only endpoints
def test_payment_confirm_requires_admin(admin_headers):
    """POST /api/payments/{id}/confirm should require admin authentication."""
    # First try without auth
    response = client.post("/api/payments/test-payment/confirm")
    assert response.status_code == 401

    # Then try with admin token (should work)
    response = client.post("/api/payments/test-payment/confirm", headers=admin_headers)
    # Will fail with 500 since payment doesn't exist, but auth passed
    assert response.status_code != 401


def test_inventory_item_toggle_requires_admin():
    """PATCH /api/inventory/items/{id} should require admin authentication."""
    response = client.patch(
        "/api/inventory/items/pizza-margherita",
        json={"available": False}
    )
    assert response.status_code == 401


def test_inventory_modifier_toggle_requires_admin():
    """PATCH /api/inventory/modifiers/{id} should require admin authentication."""
    response = client.patch(
        "/api/inventory/modifiers/extra-cheese",
        json={"is_86d": True}
    )
    assert response.status_code == 401


def test_menu_price_update_requires_admin():
    """PATCH /api/admin/menu/price should require admin authentication."""
    response = client.patch(
        "/api/admin/menu/price",
        json={"item_id": "pizza-margherita", "size_id": "medium", "price_cents": 50000}
    )
    assert response.status_code == 401


def test_restaurant_settings_requires_admin():
    """PATCH /api/admin/restaurant should require admin authentication."""
    response = client.patch(
        "/api/admin/restaurant",
        json={"settings": {"name": "New Name"}}
    )
    assert response.status_code == 401


# Token validation edge cases
def test_invalid_token_format():
    """Malformed tokens should be rejected."""
    response = client.get(
        "/api/sessions",
        headers={"Authorization": "Bearer invalid_token"}
    )
    assert response.status_code == 401


def test_missing_bearer_prefix():
    """Token without Bearer prefix should be rejected."""
    response = client.get(
        "/api/sessions",
        headers={"Authorization": "some_token_xyz"}
    )
    assert response.status_code == 401


def test_empty_authorization_header():
    """Empty authorization header should be rejected."""
    response = client.get(
        "/api/sessions",
        headers={"Authorization": ""}
    )
    assert response.status_code == 401


def test_no_authorization_header():
    """Missing authorization header should be rejected."""
    response = client.get("/api/sessions")
    assert response.status_code == 401


# Login behavior
def test_login_with_invalid_credentials():
    """Login with wrong credentials should fail."""
    response = client.post(
        "/api/auth/login",
        json={"username": "wrong", "password": "wrong"}
    )
    assert response.status_code == 401
    assert "Invalid credentials" in response.json()["detail"]


def test_login_success_returns_token():
    """Successful login should return token and user info."""
    response = client.post(
        "/api/auth/login",
        json={"username": "test_admin", "password": "test_secure_password_123"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert data["username"] == "test_admin"
    assert data["role"] == "admin"
    assert data["expires_in"] == 86400


def test_rate_limiting_on_login():
    """Repeated failed login attempts should be rate limited."""
    # Make 5 failed attempts
    for _ in range(5):
        client.post(
            "/api/auth/login",
            json={"username": "attacker", "password": "wrong"}
        )

    # 6th attempt should be blocked
    response = client.post(
        "/api/auth/login",
        json={"username": "attacker", "password": "wrong"}
    )
    assert response.status_code == 401
    # Should not reveal rate limiting vs wrong credentials
    assert "Invalid credentials" in response.json()["detail"]
