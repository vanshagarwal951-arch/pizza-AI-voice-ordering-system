"""Tests for Part 6 — Landing Page, Design System, and Frontend Routing."""

import os
os.environ["ADMIN_USERNAME"] = "test_admin"
os.environ["ADMIN_PASSWORD"] = "test_secure_password_123"
os.environ["AUTH_SECRET"] = "test_secret_key_for_hmac_signing_xyz"

from fastapi.testclient import TestClient
from web.main import app

client = TestClient(app)


def test_landing_page_served_at_root():
    """GET / should serve the landing page with 200 OK and expected HTML content."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    html = response.text
    # Verify title and branding
    assert "DIALOG Pizza" in html
    assert "Your Next Restaurant Order Starts with a Conversation." in html
    assert "AI-powered voice ordering assistant" in html
    # Verify key sections exist
    assert 'id="how-it-works"' in html
    assert 'id="features"' in html
    assert "How an Order Flows" in html
    assert "Built for Real Restaurants" in html
    # Verify simulated demo content is explicitly labeled
    assert "Simulated demo conversation" in html
    # Verify links to dashboard exist
    assert "/dashboard" in html


def test_dashboard_served_at_dashboard_route():
    """GET /dashboard should serve the operator dashboard with 200 OK."""
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    html = response.text
    # Verify dashboard elements
    assert "DIALOG — Dashboard" in html
    assert 'id="overview"' in html
    assert 'id="menu"' in html
    assert 'id="order"' in html
    assert 'id="kitchen"' in html
    assert 'id="analytics"' in html
    assert 'id="chat"' in html
    assert 'id="admin"' in html
    # Verify back-to-home link
    assert 'href="/"' in html


def test_design_system_css_served():
    """GET /static/css/design-system.css should be served with 200 OK."""
    response = client.get("/static/css/design-system.css")
    assert response.status_code == 200
    assert "text/css" in response.headers.get("content-type", "")
    css = response.text
    # Check design system variables
    assert "--bg:" in css
    assert "--accent:" in css
    assert "--font-display:" in css
    assert "--font-body:" in css
    assert "ds-btn" in css
    assert "ds-card" in css
    assert "ds-badge" in css
    assert "ds-stat-card" in css


def test_dashboard_css_served():
    """GET /static/css/app.css should be served with 200 OK."""
    response = client.get("/static/css/app.css")
    assert response.status_code == 200
    assert "text/css" in response.headers.get("content-type", "")
    css = response.text
    assert ".app" in css
    assert ".sidebar" in css
    assert ".kds-grid" in css
    assert ".mobile-topbar" in css


def test_security_headers_on_landing_page():
    """Landing page should include all security headers and updated CSP."""
    response = client.get("/")
    assert response.status_code == 200
    headers = response.headers
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("x-frame-options") == "SAMEORIGIN"
    csp = headers.get("content-security-policy", "")
    assert "fonts.googleapis.com" in csp
    assert "fonts.gstatic.com" in csp
