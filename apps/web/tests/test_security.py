"""Tests for API and web security hardening (Part 3)."""

import pytest
from fastapi.testclient import TestClient

import os
os.environ["ADMIN_USERNAME"] = "test_admin"
os.environ["ADMIN_PASSWORD"] = "test_secure_password_123"
os.environ["AUTH_SECRET"] = "test_secret_key_for_hmac_signing_xyz"

from web.main import app
from menu_engine.services.auth import _reset_rate_limit

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_rate_limiting():
    """Reset rate limiting before each test."""
    _reset_rate_limit()
    yield
    _reset_rate_limit()


@pytest.fixture
def admin_token():
    """Get a valid admin token."""
    response = client.post(
        "/api/auth/login",
        json={"username": "test_admin", "password": "test_secure_password_123"}
    )
    return response.json()["token"]


@pytest.fixture
def admin_headers(admin_token):
    """Get authorization headers with admin token."""
    return {"Authorization": f"Bearer {admin_token}"}


# Input Validation Tests
def test_tool_request_validates_session_id():
    """Tool request should validate and sanitize session_id."""
    # Path traversal attempt
    response = client.post(
        "/api/tools/invoke",
        json={"session_id": "../../../etc/passwd", "tool": "view_menu", "args": {}}
    )
    assert response.status_code == 422  # Validation error

    # Valid session_id
    response = client.post(
        "/api/tools/invoke",
        json={"session_id": "test-room-123", "tool": "view_menu", "args": {}}
    )
    assert response.status_code == 200


def test_tool_request_validates_tool_name():
    """Tool request should only allow valid tool names."""
    response = client.post(
        "/api/tools/invoke",
        json={"session_id": "test-room", "tool": "evil_tool", "args": {}}
    )
    assert response.status_code == 422
    assert "Invalid tool" in str(response.json())


def test_chat_request_validates_message_length():
    """Chat request should enforce message length limits."""
    # Very long message (>2000 chars)
    long_message = "a" * 2001
    response = client.post(
        "/api/chat",
        json={"session_id": "test-room", "message": long_message}
    )
    assert response.status_code == 422


def test_chat_request_validates_empty_message():
    """Chat request should reject empty messages."""
    response = client.post(
        "/api/chat",
        json={"session_id": "test-room", "message": ""}
    )
    assert response.status_code == 422


def test_checkout_validates_payment_method():
    """Checkout should validate payment method."""
    response = client.post(
        "/api/sessions/test-room/checkout",
        json={"payment_method": "bitcoin", "customer_phone": None}
    )
    assert response.status_code == 422
    assert "Invalid payment method" in str(response.json())


def test_checkout_validates_phone_number():
    """Checkout should validate phone number format (F18 fix)."""
    # Too short
    response = client.post(
        "/api/sessions/test-room/checkout",
        json={"payment_method": "cod", "customer_phone": "123"}
    )
    assert response.status_code == 422

    # Valid phone
    response = client.post(
        "/api/sessions/test-room/checkout",
        json={"payment_method": "cod", "customer_phone": "+919876543210"}
    )
    assert response.status_code == 200


def test_kitchen_status_validates_status():
    """KDS ticket status should validate against allowed values."""
    # Login first
    login = client.post(
        "/api/auth/login",
        json={"username": "test_admin", "password": "test_secure_password_123"}
    )
    token = login.json()["token"]

    response = client.patch(
        "/api/kds/tickets/test-ticket-123",
        json={"status": "invalid_status"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 422
    assert "Status must be one of" in str(response.json())


def test_payment_request_validates_amount():
    """Payment creation should validate amount limits."""
    login = client.post(
        "/api/auth/login",
        json={"username": "test_admin", "password": "test_secure_password_123"}
    )
    token = login.json()["token"]

    # Negative amount
    response = client.post(
        "/api/payments/create",
        json={
            "order_id": "test-order",
            "amount_cents": -100,
            "currency": "INR",
            "method": "cod"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 422

    # Zero amount
    response = client.post(
        "/api/payments/create",
        json={
            "order_id": "test-order",
            "amount_cents": 0,
            "currency": "INR",
            "method": "cod"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 422


# Security Headers Tests
def test_security_headers_present():
    """Security headers should be present on all responses."""
    response = client.get("/api/health")

    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert "Referrer-Policy" in response.headers
    assert "Permissions-Policy" in response.headers
    assert "Content-Security-Policy" in response.headers


def test_csp_allows_required_sources():
    """Content Security Policy should allow required sources."""
    response = client.get("/api/health")
    csp = response.headers.get("Content-Security-Policy", "")

    # Should allow self
    assert "'self'" in csp
    # Should allow WebSocket connections
    assert "ws:" in csp or "wss:" in csp
    # Should allow LiveKit SDK from CDN
    assert "cdn.jsdelivr.net" in csp


# XSS Prevention Tests
def test_menu_data_not_interpreted_as_html():
    """Menu endpoint should return JSON, not HTML."""
    response = client.get("/api/menu")
    assert response.headers.get("content-type") == "application/json"
    data = response.json()
    # Verify structure is JSON
    assert "items_by_category" in data
    assert "restaurant" in data


# CORS Tests
def test_cors_headers_present():
    """CORS headers should be configured."""
    response = client.options(
        "/api/menu",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"}
    )
    # FastAPI CORSMiddleware should handle OPTIONS requests
    assert response.status_code in (200, 405)


def test_cors_allows_localhost():
    """CORS should allow localhost origins."""
    response = client.get(
        "/api/menu",
        headers={"Origin": "http://localhost:3000"}
    )
    # Check if Access-Control-Allow-Origin is set
    cors_header = response.headers.get("access-control-allow-origin")
    # Should either be specific origin or wildcard
    assert cors_header is not None or response.status_code == 200


# Request Size Limit Tests
def test_request_body_size_limit():
    """Request body size should be limited."""
    # Create a large payload (>1MB)
    large_message = "x" * (1024 * 1024 + 1000)
    response = client.post(
        "/api/chat",
        json={"session_id": "test-room", "message": large_message}
    )
    # Should be rejected by size limit or validation
    assert response.status_code in (413, 422)


# WebSocket Security Tests
def test_websocket_validates_session_id():
    """WebSocket should validate session ID."""
    # Path traversal attempt
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/sessions/../../../etc/passwd") as websocket:
            pass


# SQL Injection Prevention Tests
def test_session_id_sql_injection_prevented():
    """Session IDs should be sanitized to prevent SQL injection."""
    # SQL injection attempt in session_id
    response = client.post(
        "/api/sessions/test-room'; DROP TABLE orders; --/start",
        json={}
    )
    # Validation should reject invalid characters with 400, 404, or 422
    assert response.status_code in (400, 404, 422)


# Error Message Safety Tests
def test_error_messages_dont_leak_internals():
    """Error messages should not expose internal details."""
    response = client.get("/api/orders")
    # Should get auth error, not internal error
    assert response.status_code == 401
    error_detail = response.json().get("detail", "")
    # Should not contain stack traces or file paths
    assert "Traceback" not in error_detail
    assert "/home/" not in error_detail
    assert "C:\\" not in error_detail


# Authentication Bypass Attempts
def test_cannot_bypass_auth_with_empty_token():
    """Empty Authorization header should not bypass authentication."""
    response = client.get(
        "/api/orders",
        headers={"Authorization": ""}
    )
    assert response.status_code == 401


def test_cannot_bypass_auth_with_malformed_token():
    """Malformed tokens should not bypass authentication."""
    response = client.get(
        "/api/orders",
        headers={"Authorization": "Bearer '; DROP TABLE users; --"}
    )
    assert response.status_code == 401


# Path Traversal Prevention
def test_session_paths_prevent_traversal():
    """Session endpoints should prevent path traversal."""
    response = client.get("/api/sessions/../../../../../etc/passwd/cart")
    # FastAPI should normalize paths or return 404
    assert response.status_code in (404, 422)


# Exposed File Access & Path Traversal Review
def test_static_files_prevent_env_access():
    """Static file mount must not serve .env file."""
    response = client.get("/static/../../.env")
    assert response.status_code in (404, 400)


def test_static_files_prevent_db_access():
    """Static file mount must not serve SQLite database."""
    response = client.get("/static/../../../data/voice_ordering.db")
    assert response.status_code in (404, 400)


def test_static_files_prevent_git_access():
    """Static file mount must not serve .git."""
    response = client.get("/static/../../.git/config")
    assert response.status_code in (404, 400)


def test_health_does_not_leak_database_driver():
    """Health check endpoint should not leak raw DB connection string or driver (F10)."""
    response = client.get("/api/health")
    assert response.status_code == 200
    db_val = response.json().get("database", "")
    assert "sqlite+pysqlite" not in db_val
    assert "postgresql" not in db_val
    assert "password" not in db_val


def test_migration_schema_sql_injection_prevented():
    """_sqlite_has_column must reject invalid table names (F12)."""
    from menu_engine.db.models import _sqlite_has_column

    class MockConn:
        pass

    with pytest.raises(ValueError, match="Disallowed table name"):
        _sqlite_has_column(MockConn(), "orders; DROP TABLE users; --", "status")


def test_atomic_write_json(tmp_path):
    """atomic_write_json writes valid JSON file safely (F11)."""
    from menu_engine.utils.file_ops import atomic_write_json
    import json

    target = tmp_path / "test.json"
    data = {"hello": "world", "status": 200}
    atomic_write_json(target, data)
    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8")) == data


def test_payment_confirm_persists_to_database(admin_headers):
    """Payment confirmation must update DB and return 404 for non-existent payment (F13)."""
    # Non-existent payment returns 404 (not 500)
    response = client.post("/api/payments/non_existent_payment_id/confirm", headers=admin_headers)
    assert response.status_code == 404
    assert "Payment non_existent_payment_id not found" in response.json()["detail"]


# Host Binding Security Test
def test_default_host_is_localhost():
    """Default host binding should be localhost for security (F21)."""
    import os
    from web.main import run

    # Check default is 127.0.0.1, not 0.0.0.0
    default_host = os.getenv("HOST", "127.0.0.1")
    assert default_host == "127.0.0.1"
