"""Staff authentication for dashboard admin routes with proper password hashing and rate limiting."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

# Simple in-memory rate limiting (reset on server restart)
_login_attempts: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 300  # 5 minutes
_MAX_ATTEMPTS = 5


def _reset_rate_limit(identifier: str | None = None) -> None:
    """Reset rate limiting for testing. If identifier is None, clears all."""
    if identifier is None:
        _login_attempts.clear()
    elif identifier in _login_attempts:
        del _login_attempts[identifier]


def get_admin_password() -> str:
    """Get admin password from env. Refuses to use hardcoded default."""
    password = os.getenv("ADMIN_PASSWORD", "").strip()
    if not password:
        raise RuntimeError(
            "ADMIN_PASSWORD must be set in .env for admin routes. "
            "Generate a strong password (e.g., with 'openssl rand -hex 16') "
            "and set it: ADMIN_PASSWORD=your_secure_password_here"
        )
    if password == "dialog2026":
        raise RuntimeError(
            "ADMIN_PASSWORD is set to the default example value 'dialog2026'. "
            "This is insecure. Generate a strong password and update .env"
        )
    return password


def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    """Hash password with PBKDF2-HMAC-SHA256 (100,000 iterations)."""
    if salt is None:
        salt = secrets.token_bytes(32)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return pwd_hash.hex(), salt.hex()


def _verify_password(password: str, expected_hash: str, salt_hex: str) -> bool:
    """Verify password against stored hash using constant-time comparison."""
    salt = bytes.fromhex(salt_hex)
    pwd_hash, _ = _hash_password(password, salt)
    return hmac.compare_digest(pwd_hash, expected_hash)


def _check_rate_limit(identifier: str) -> bool:
    """Check if identifier is rate limited. Returns True if allowed, False if blocked."""
    now = time.time()
    attempts = _login_attempts[identifier]

    # Remove old attempts outside the window
    _login_attempts[identifier] = [t for t in attempts if now - t < _RATE_LIMIT_WINDOW]

    return len(_login_attempts[identifier]) < _MAX_ATTEMPTS


def _record_login_attempt(identifier: str) -> None:
    """Record a login attempt for rate limiting."""
    _login_attempts[identifier].append(time.time())


def login(username: str, password: str, ip_address: str = "unknown") -> dict[str, Any] | None:
    """Authenticate admin user with rate limiting. Returns token dict or None on failure."""
    identifier = f"{username}:{ip_address}"

    # Check rate limit
    if not _check_rate_limit(identifier):
        _record_login_attempt(identifier)
        # Don't reveal whether rate limited to prevent username enumeration
        return None

    # Record attempt before validation
    _record_login_attempt(identifier)

    expected_user = os.getenv("ADMIN_USERNAME", "admin").strip()

    # Use constant-time comparison for username to prevent timing attacks
    username_valid = hmac.compare_digest(username.strip(), expected_user)
    password_valid = password == get_admin_password()

    if not (username_valid and password_valid):
        # Generic error - don't reveal which part failed
        return None

    token = _issue_token(username, "admin")
    return {"token": token, "username": username, "role": "admin", "expires_in": 86400}


def verify_token(token: str) -> dict[str, str] | None:
    """Verify auth token and return payload dict with username and role, or None if invalid."""
    if not token or "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    expected = hmac.new(_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        parts = payload.split("|")
        if len(parts) != 3:
            return None
        username, role, exp = parts
        if float(exp) <= time.time():
            return None
        return {"username": username, "role": role}
    except (ValueError, IndexError):
        return None


def verify_token_bool(token: str) -> bool:
    """Legacy boolean verification for backward compatibility."""
    return verify_token(token) is not None


def _issue_token(username: str, role: str = "admin") -> str:
    """Issue a JWT-like token with username, role, and expiration."""
    exp = str(time.time() + 86400)
    payload = f"{username}|{role}|{exp}"
    sig = hmac.new(_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _secret() -> str:
    """Get or generate auth secret. Never use hardcoded fallback."""
    secret = os.getenv("AUTH_SECRET", "").strip()
    if secret:
        return secret

    # Generate and persist a random secret for this instance
    secret_file = Path(__file__).resolve().parents[4] / ".auth_secret"
    if secret_file.exists():
        return secret_file.read_text(encoding="utf-8").strip()

    # First run - generate new secret
    new_secret = secrets.token_hex(32)
    secret_file.write_text(new_secret, encoding="utf-8")
    secret_file.chmod(0o600)  # Read/write owner only (Unix)

    import warnings
    warnings.warn(
        f"Generated new AUTH_SECRET and saved to {secret_file}. "
        "For production, set AUTH_SECRET in .env instead of using the auto-generated file.",
        RuntimeWarning,
        stacklevel=2
    )

    return new_secret
