"""Tests for authentication and authorization."""

import os
import time
import pytest
from menu_engine.services.auth import (
    login,
    verify_token,
    verify_token_bool,
    _check_rate_limit,
    _record_login_attempt,
    _reset_rate_limit,
    _hash_password,
    _verify_password,
)


@pytest.fixture(autouse=True)
def preserve_env_and_rate_limits():
    """Preserve environment variables and reset rate limits to avoid polluting other test suites."""
    old_env = dict(os.environ)
    _reset_rate_limit()
    yield
    os.environ.clear()
    os.environ.update(old_env)
    _reset_rate_limit()


def test_password_hashing():
    """Test password hashing with PBKDF2."""
    password = "test_password_123"
    pwd_hash, salt_hex = _hash_password(password)

    # Hash should be deterministic with same salt
    pwd_hash2, _ = _hash_password(password, bytes.fromhex(salt_hex))
    assert pwd_hash == pwd_hash2

    # Different salt should produce different hash
    pwd_hash3, salt_hex3 = _hash_password(password)
    assert pwd_hash != pwd_hash3
    assert salt_hex != salt_hex3


def test_password_verification():
    """Test password verification."""
    password = "correct_password"
    wrong_password = "wrong_password"

    pwd_hash, salt_hex = _hash_password(password)

    # Correct password should verify
    assert _verify_password(password, pwd_hash, salt_hex)

    # Wrong password should not verify
    assert not _verify_password(wrong_password, pwd_hash, salt_hex)


def test_rate_limiting():
    """Test rate limiting for login attempts."""
    identifier = "test_user_rate_limit"

    # First 5 attempts should be allowed
    for i in range(5):
        assert _check_rate_limit(identifier)
        _record_login_attempt(identifier)

    # 6th attempt should be blocked
    assert not _check_rate_limit(identifier)


def test_login_with_invalid_credentials():
    """Test login with invalid credentials."""
    import os

    # Set test credentials
    os.environ["ADMIN_USERNAME"] = "test_admin"
    os.environ["ADMIN_PASSWORD"] = "secure_test_password_123"

    # Wrong username
    result = login("wrong_user", "secure_test_password_123", "127.0.0.1")
    assert result is None

    # Wrong password
    result = login("test_admin", "wrong_password", "127.0.0.1")
    assert result is None

    # Both wrong
    result = login("wrong_user", "wrong_password", "127.0.0.1")
    assert result is None


def test_login_with_valid_credentials():
    """Test login with valid credentials."""
    import os

    os.environ["ADMIN_USERNAME"] = "test_admin"
    os.environ["ADMIN_PASSWORD"] = "secure_test_password_456"

    result = login("test_admin", "secure_test_password_456", "127.0.0.1")
    assert result is not None
    assert "token" in result
    assert result["username"] == "test_admin"
    assert result["role"] == "admin"
    assert result["expires_in"] == 86400


def test_token_verification():
    """Test token verification."""
    import os

    os.environ["ADMIN_USERNAME"] = "test_admin"
    os.environ["ADMIN_PASSWORD"] = "secure_test_password_789"

    # Get a valid token
    result = login("test_admin", "secure_test_password_789", "127.0.0.1")
    token = result["token"]

    # Verify token
    user_info = verify_token(token)
    assert user_info is not None
    assert user_info["username"] == "test_admin"
    assert user_info["role"] == "admin"

    # Boolean verification
    assert verify_token_bool(token)


def test_token_verification_invalid():
    """Test token verification with invalid tokens."""
    # Empty token
    assert verify_token("") is None
    assert not verify_token_bool("")

    # Malformed token
    assert verify_token("invalid") is None
    assert not verify_token_bool("invalid")

    # Wrong signature
    assert verify_token("admin|staff|9999999999.wrongsig") is None


def test_token_expiration():
    """Test expired token rejection."""
    import os

    os.environ["ADMIN_USERNAME"] = "test_admin"
    os.environ["ADMIN_PASSWORD"] = "secure_test_password_exp"

    # Create token with short expiration by manipulating time
    from menu_engine.services.auth import _issue_token

    # Issue token
    token = _issue_token("test_admin", "admin")

    # Verify it's valid
    assert verify_token(token) is not None

    # Manually create expired token by editing payload
    # Format: username|role|expiration.signature
    payload = f"test_admin|admin|{time.time() - 1}"  # Already expired
    import hmac
    import hashlib
    from menu_engine.services.auth import _secret
    sig = hmac.new(_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()
    expired_token = f"{payload}.{sig}"

    # Expired token should fail verification
    assert verify_token(expired_token) is None
    assert not verify_token_bool(expired_token)


def test_admin_password_requirements():
    """Test admin password validation."""
    import os
    from menu_engine.services.auth import get_admin_password

    # Empty password should raise error
    os.environ["ADMIN_PASSWORD"] = ""
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD must be set"):
        get_admin_password()

    # Default password should raise error
    os.environ["ADMIN_PASSWORD"] = "dialog2026"
    with pytest.raises(RuntimeError, match="default example value"):
        get_admin_password()

    # Valid password should work
    os.environ["ADMIN_PASSWORD"] = "valid_secure_password"
    assert get_admin_password() == "valid_secure_password"


def test_login_rate_limiting_by_ip():
    """Test that rate limiting works per IP address."""
    import os

    os.environ["ADMIN_USERNAME"] = "test_admin"
    os.environ["ADMIN_PASSWORD"] = "secure_password_rate_test"

    # First IP can make 5 attempts
    for i in range(5):
        result = login("test_admin", "wrong_password", "192.168.1.100")
        assert result is None  # Wrong password

    # 6th attempt from same IP should be blocked (returns None)
    result = login("test_admin", "secure_password_rate_test", "192.168.1.100")
    assert result is None  # Blocked by rate limit even though password is correct

    # Different IP should still work
    result = login("test_admin", "secure_password_rate_test", "192.168.1.200")
    assert result is not None  # Different IP not rate limited
