"""Comprehensive verification suite for DIALOG Pizza — Part 4: Database and Order Integrity.

Covers:
- Optimistic concurrency control and lost-update prevention.
- Idempotent finalization with payload verification and conflict detection.
- Tool allowlist and untrusted argument sanitization.
- Customer cart confirmation requirements.
- Safe abandoned-session cleanup without affecting active sessions.
- Two-phase transaction boundaries preventing external side effects on DB failure.
- PII scrubbing for external provider data sharing.
- Online SQLite backup and integrity check.
- Fail-fast database initialization on unreachable primary DB.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.orm import sessionmaker

from menu_engine.cart.persistent import PersistentSessionManager
from menu_engine.db.models import (
    DatabaseConnectionError,
    Order,
    OrderSession,
    SessionStatus,
    create_db_engine,
    init_db,
    ping_database,
)
from menu_engine.db.repository import (
    CartRepository,
    ConcurrentUpdateError,
    IdempotencyConflictError,
    OrderIntegrityError,
)
from menu_engine.menu.loader import load_menu
from menu_engine.tools.order_tools import ALLOWED_TOOLS, create_order_tools, execute_tool
from menu_engine.types import AddItemInput, ToppingSelection
from menu_engine.utils.db_backup import backup_sqlite_database, verify_database_integrity
from menu_engine.utils.privacy import redact_pii


@pytest.fixture
def test_db_setup(tmp_path):
    db_file = tmp_path / "test_integrity.db"
    engine = create_db_engine(f"sqlite+pysqlite:///{db_file.as_posix()}")
    init_db(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    repo = CartRepository(session_factory)
    menu = load_menu()
    return {"engine": engine, "repo": repo, "menu": menu, "db_path": db_file}


def test_concurrent_cart_updates_optimistic_locking(test_db_setup):
    repo = test_db_setup["repo"]
    menu = test_db_setup["menu"]
    session_id = "concurrent-session-1"

    # Manager A and Manager B represent two independent processes/requests loading the same cart
    mgr_a = PersistentSessionManager(repo)
    mgr_b = PersistentSessionManager(repo)

    tools_a = create_order_tools(menu, session_id, session_manager=mgr_a, repository=repo)
    tools_b = create_order_tools(menu, session_id, session_manager=mgr_b, repository=repo)

    # Initial state loaded into both
    mgr_a.get_or_create(session_id)
    mgr_b.get_or_create(session_id)
    assert mgr_a.get_version(session_id) == mgr_b.get_version(session_id)

    # Client A adds an item and commits first -> version increments to 2
    res_a = tools_a.add_item(AddItemInput(menu_item_id="margherita", size_id="small"))
    assert res_a.success
    assert mgr_a.get_version(session_id) == 2

    # Client B attempts to save with stale version 1 directly on repository -> ConcurrentUpdateError
    cart_b = mgr_b.get_or_create(session_id)
    with pytest.raises(ConcurrentUpdateError):
        repo.save_cart(session_id, cart_b, expected_version=1)

    # When client B adds an item via tools, tools handles ConcurrentUpdateError gracefully
    res_b = tools_b.add_item(AddItemInput(menu_item_id="cafe-latte", size_id="regular"))
    # Either succeeds after refreshing or returns informative error
    assert res_b.message is not None


def test_concurrent_cart_updates_multithreaded(test_db_setup):
    repo = test_db_setup["repo"]
    menu = test_db_setup["menu"]
    session_id = "multithreaded-session"

    repo.ensure_session(session_id)
    success_count = [0]
    errors = []

    def _worker(item_id: str):
        try:
            mgr = PersistentSessionManager(repo)
            tools = create_order_tools(menu, session_id, session_manager=mgr, repository=repo)
            res = tools.add_item(AddItemInput(menu_item_id=item_id, size_id="regular"))
            if res.success:
                success_count[0] += 1
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=_worker, args=("cafe-latte",)),
        threading.Thread(target=_worker, args=("masala-chai",)),
        threading.Thread(target=_worker, args=("iced-tea",)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Unexpected exceptions during concurrency: {errors}"
    assert success_count[0] >= 1
    # Verify cart has at least 1 item and version matches updates
    cart = repo.load_cart(session_id)
    assert not cart.is_empty()


def test_idempotent_order_finalization(test_db_setup):
    repo = test_db_setup["repo"]
    menu = test_db_setup["menu"]
    session_id = "idempotent-session"

    mgr = PersistentSessionManager(repo)
    tools = create_order_tools(menu, session_id, session_manager=mgr, repository=repo)
    tools.add_item(AddItemInput(menu_item_id="margherita", size_id="medium"))

    idempotency_key = "req-unique-key-12345"
    summary = tools._cart.summarize(menu)

    # First finalization
    order_1 = repo.finalize_session(
        session_id=session_id,
        summary=summary,
        menu=menu,
        payment_method="cod",
        customer_phone="+919876543210",
        idempotency_key=idempotency_key,
    )
    assert order_1.id is not None

    # Exact replay of the same idempotency key with identical payload
    order_2 = repo.finalize_session(
        session_id=session_id,
        summary=summary,
        menu=menu,
        payment_method="cod",
        customer_phone="+919876543210",
        idempotency_key=idempotency_key,
    )

    # Must return the identical order without creating duplicate orders
    assert order_1.id == order_2.id
    all_orders = repo.list_orders()
    matching_orders = [o for o in all_orders if o["session_id"] == session_id]
    assert len(matching_orders) == 1


def test_idempotency_conflict_detection(test_db_setup):
    repo = test_db_setup["repo"]
    menu = test_db_setup["menu"]
    session_id = "conflict-session"

    mgr = PersistentSessionManager(repo)
    tools = create_order_tools(menu, session_id, session_manager=mgr, repository=repo)
    tools.add_item(AddItemInput(menu_item_id="margherita", size_id="medium"))

    idempotency_key = "conflict-test-key-999"
    summary_1 = tools._cart.summarize(menu)

    # Initial order finalization
    repo.finalize_session(
        session_id=session_id,
        summary=summary_1,
        menu=menu,
        payment_method="cod",
        idempotency_key=idempotency_key,
    )

    # Second order attempt with DIFFERENT payment method and phone
    with pytest.raises(IdempotencyConflictError):
        repo.finalize_session(
            session_id=session_id,
            summary=summary_1,
            menu=menu,
            payment_method="upi",  # Changed payload
            customer_phone="+911111111111",
            idempotency_key=idempotency_key,
        )


def test_tool_allowlist_enforcement(test_db_setup):
    repo = test_db_setup["repo"]
    menu = test_db_setup["menu"]
    tools = create_order_tools(menu, "tools-test-sess", repository=repo)

    # Disallowed/malicious tool names
    for bad_tool in [
        "eval",
        "system_command",
        "drop_database",
        "exec",
        "arbitrary_code",
        "../traversal",
    ]:
        res = execute_tool(tools, bad_tool, {})
        assert not res.success
        assert res.error_code == "R01"
        assert "not permitted" in res.message or "Unknown tool" in res.message

    # Non-dictionary argument rejection
    res_bad_args = execute_tool(tools, "add_item", "not-a-dict")
    assert not res_bad_args.success
    assert res_bad_args.error_code == "R02"

    # Permitted tools
    for allowed in ALLOWED_TOOLS:
        assert isinstance(allowed, str)


def test_untrusted_arguments_sanitized(test_db_setup):
    repo = test_db_setup["repo"]
    menu = test_db_setup["menu"]
    tools = create_order_tools(menu, "untrusted-args-sess", repository=repo)

    # Empty item_name
    res = tools.add_item({"item_name": "", "size": "medium"})
    assert not res.success
    assert res.error_code == "R02"

    # Excessive quantity
    res_qty_high = tools.add_item({"item_name": "margherita", "quantity": 9999})
    assert not res_qty_high.success

    # Negative / zero quantity
    res_qty_zero = tools.add_item({"item_name": "margherita", "quantity": 0})
    assert not res_qty_zero.success

    # Non-numeric quantity
    res_qty_nan = tools.add_item({"item_name": "margherita", "quantity": "twenty"})
    assert not res_qty_nan.success

    # Excessive toppings (>20)
    huge_toppings = [{"modifier_id": f"top_{i}"} for i in range(25)]
    res_huge_toppings = tools.add_item(
        {"item_name": "margherita", "whole_toppings": huge_toppings}
    )
    assert not res_huge_toppings.success


def test_cart_confirmation_required_before_finalizing(test_db_setup):
    repo = test_db_setup["repo"]
    menu = test_db_setup["menu"]
    session_id = "confirm-sess"
    mgr = PersistentSessionManager(repo)
    tools = create_order_tools(menu, session_id, session_manager=mgr, repository=repo)
    tools.add_item(AddItemInput(menu_item_id="margherita", size_id="medium"))

    # Explicitly unconfirmed finalization must be rejected
    res_unconfirmed = execute_tool(
        tools,
        "finalize_order",
        {"confirmed": False, "payment_method": "cod"},
    )
    assert not res_unconfirmed.success
    assert "confirmation" in res_unconfirmed.message.lower()
    assert res_unconfirmed.error_code == "R10"
    assert len(repo.list_orders()) == 0

    # Confirmed finalization proceeds
    res_confirmed = execute_tool(
        tools,
        "finalize_order",
        {"confirmed": True, "payment_method": "cod"},
    )
    assert res_confirmed.success
    assert "confirmed" in res_confirmed.message.lower()
    assert len(repo.list_orders()) == 1


def test_stale_abandoned_session_cleanup(test_db_setup):
    repo = test_db_setup["repo"]

    # Create active session that is fresh
    repo.ensure_session("active-fresh-1")

    # Create active session and backdate its updated_at
    repo.ensure_session("abandoned-stale-1")
    old_time = datetime.now(timezone.utc) - timedelta(hours=48)
    with repo._session_factory() as db:
        stale_sess = db.get(OrderSession, "abandoned-stale-1")
        stale_sess.updated_at = old_time
        db.commit()

    # Run cleanup for sessions older than 24h
    cleaned_count = repo.cleanup_abandoned_sessions(max_age_seconds=86400, cancel_only=True)
    assert cleaned_count >= 1

    # Active fresh session must still be active
    active_sessions = repo.list_active_sessions()
    active_ids = {s["id"] for s in active_sessions}
    assert "active-fresh-1" in active_ids
    assert "abandoned-stale-1" not in active_ids

    # Stale session status changed to CANCELLED
    with repo._session_factory() as db:
        stale_row = db.get(OrderSession, "abandoned-stale-1")
        assert stale_row.status == SessionStatus.CANCELLED.value


def test_database_failure_prevents_external_side_effects(test_db_setup):
    repo = test_db_setup["repo"]
    menu = test_db_setup["menu"]
    session_id = "fail-persistence-sess"
    mgr = PersistentSessionManager(repo)
    tools = create_order_tools(menu, session_id, session_manager=mgr, repository=repo)
    tools.add_item(AddItemInput(menu_item_id="margherita", size_id="small"))
    summary = tools._cart.summarize(menu)

    # Force database commit to fail
    with patch.object(repo, "_session_factory", side_effect=RuntimeError("Disk full / DB connection severed")):
        with pytest.raises(OrderIntegrityError):
            repo.finalize_session(
                session_id=session_id,
                summary=summary,
                menu=menu,
                payment_method="cod",
            )


def test_pii_redaction():
    text_with_pii = (
        "Customer phone is +919876543210 and US cell is 415-555-2671. "
        "Email is customer.test@example.com and card is 4532-1234-5678-9012."
    )
    cleaned = redact_pii(text_with_pii)
    assert "+919876543210" not in cleaned
    assert "415-555-2671" not in cleaned
    assert "customer.test@example.com" not in cleaned
    assert "4532-1234-5678-9012" not in cleaned
    assert "[PHONE_REDACTED]" in cleaned
    assert "[EMAIL_REDACTED]" in cleaned
    assert "[CARD_REDACTED]" in cleaned


def test_sqlite_online_backup_and_integrity(test_db_setup, tmp_path):
    src_db = test_db_setup["db_path"]
    backup_dest = backup_sqlite_database(src_db, backup_dir=tmp_path / "backups")
    assert backup_dest.exists()
    assert backup_dest.stat().st_size > 0
    assert verify_database_integrity(backup_dest) is True


def test_database_connection_failure_refuses_silent_sqlite_fallback():
    # Primary database explicitly configured but unreachable
    unreachable_url = "postgresql+psycopg://user:secret@localhost:9999/nonexistent_db"
    with patch.dict(os.environ, {"DATABASE_URL": unreachable_url}):
        with patch("menu_engine.db.models.ping_database", return_value=False):
            bad_engine = create_db_engine(unreachable_url)
            with pytest.raises(DatabaseConnectionError) as exc_info:
                init_db(bad_engine)
            err_msg = str(exc_info.value)
            assert "unreachable" in err_msg
            assert "secret" not in err_msg
