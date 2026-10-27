from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker, selectinload

from menu_engine.cart.cart import Cart
from menu_engine.db.models import (
    CallLog,
    CartItemRow,
    KitchenTicket,
    Order,
    OrderSession,
    Payment,
    PosSubmission,
    SessionStatus,
    create_db_engine,
    init_db,
)
from menu_engine.pricing import calculate_order_totals
from menu_engine.services.inventory import decrement_stock
from menu_engine.services.kitchen import write_kitchen_ticket
from menu_engine.services.notifications import notify_order_finalized
from menu_engine.services.payments import create_payment
from menu_engine.services.pos import submit_to_pos
from menu_engine.services.post_call_judge import run_post_call_judge
from menu_engine.services.sms import send_order_sms
from menu_engine.types import CartLineItem, CartSummary, MenuData, ToppingSelection

logger = logging.getLogger(__name__)


class ConcurrentUpdateError(RuntimeError):
    """Raised when concurrent modifications to the cart or session are detected."""


class IdempotencyConflictError(ValueError):
    """Raised when the same idempotency key is reused with a different order payload."""


class OrderIntegrityError(RuntimeError):
    """Raised when durable order persistence fails."""


_session_locks: dict[str, threading.RLock] = defaultdict(threading.RLock)
_locks_guard = threading.Lock()


def _get_session_lock(session_id: str) -> threading.RLock:
    with _locks_guard:
        return _session_locks[session_id]


def _toppings_to_json(toppings: list[ToppingSelection]) -> str:
    return json.dumps([{"modifier_id": t.modifier_id, "extra": t.extra} for t in toppings])


def _toppings_from_json(raw: str) -> list[ToppingSelection]:
    data = json.loads(raw or "[]")
    return [ToppingSelection(modifier_id=t["modifier_id"], extra=t.get("extra", False)) for t in data]


def _row_to_line(row: CartItemRow) -> CartLineItem:
    return CartLineItem(
        id=row.id,
        menu_item_id=row.menu_item_id,
        menu_item_name=row.menu_item_name,
        size_id=row.size_id,
        size_name=row.size_name,
        is_half_and_half=row.is_half_and_half,
        left_toppings=_toppings_from_json(row.left_toppings),
        right_toppings=_toppings_from_json(row.right_toppings),
        whole_toppings=_toppings_from_json(row.whole_toppings),
        crust_id=row.crust_id,
        line_total_cents=row.line_total_cents,
        quantity=row.quantity,
    )


def _line_to_row(session_id: str, line: CartLineItem) -> CartItemRow:
    return CartItemRow(
        id=line.id,
        session_id=session_id,
        menu_item_id=line.menu_item_id,
        menu_item_name=line.menu_item_name,
        size_id=line.size_id,
        size_name=line.size_name,
        is_half_and_half=line.is_half_and_half,
        left_toppings=_toppings_to_json(line.left_toppings),
        right_toppings=_toppings_to_json(line.right_toppings),
        whole_toppings=_toppings_to_json(line.whole_toppings),
        crust_id=line.crust_id,
        line_total_cents=line.line_total_cents,
        quantity=line.quantity,
    )


def _compute_payload_hash(
    session_id: str,
    total_cents: int,
    currency: str,
    summary: CartSummary,
    payment_method: str,
    customer_phone: str | None,
) -> str:
    """Compute deterministic SHA-256 hash of order parameters for idempotency payload verification."""
    items_repr = sorted(
        [
            (
                item.menu_item_id,
                item.size_id,
                item.quantity,
                item.line_total_cents,
                item.is_half_and_half,
            )
            for item in summary.items
        ]
    )
    raw = json.dumps(
        {
            "session_id": session_id,
            "total_cents": total_cents,
            "currency": currency,
            "item_count": summary.item_count,
            "items": items_repr,
            "payment_method": payment_method.lower().strip() if payment_method else "cod",
            "customer_phone": customer_phone.strip() if customer_phone else None,
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class CartRepository:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def ensure_session(self, session_id: str, *, restart_if_finalized: bool = False) -> OrderSession:
        with _get_session_lock(session_id):
            with self._session_factory() as db:
                row = db.get(OrderSession, session_id)
                if row is None:
                    row = OrderSession(
                        id=session_id,
                        status=SessionStatus.ACTIVE.value,
                        version=1,
                        payment_method="cod",
                    )
                    db.add(row)
                    db.commit()
                elif row.status != SessionStatus.ACTIVE.value:
                    if restart_if_finalized and row.status in (
                        SessionStatus.FINALIZED.value,
                        SessionStatus.CANCELLED.value,
                    ):
                        return self._reactivate_session(db, row)
                    raise ValueError(f"Session {session_id} is not active (status={row.status})")
                db.refresh(row)
                return row

    def _reactivate_session(self, db: Session, row: OrderSession) -> OrderSession:
        """Start a fresh order on a room that previously finalized."""
        for item in list(row.cart_items):
            db.delete(item)
        row.status = SessionStatus.ACTIVE.value
        row.finalized_at = None
        row.version = (row.version or 1) + 1
        row.updated_at = datetime.now(timezone.utc)
        log = db.scalar(select(CallLog).where(CallLog.session_id == row.id))
        if log:
            db.delete(log)
        db.commit()
        db.refresh(row)
        return row

    def restart_session(self, session_id: str) -> dict[str, str]:
        """Prepare a room for a new voice or web order (clears cart if previously finalized)."""
        with _get_session_lock(session_id):
            with self._session_factory() as db:
                row = db.get(OrderSession, session_id)
                if row is None:
                    row = OrderSession(
                        id=session_id,
                        status=SessionStatus.ACTIVE.value,
                        version=1,
                        payment_method="cod",
                    )
                    db.add(row)
                    db.commit()
                    db.refresh(row)
                    return {"session_id": session_id, "status": row.status, "restarted": True}

                restarted = row.status in (
                    SessionStatus.FINALIZED.value,
                    SessionStatus.CANCELLED.value,
                )
                if restarted:
                    self._reactivate_session(db, row)
                else:
                    db.refresh(row)
                return {
                    "session_id": session_id,
                    "status": SessionStatus.ACTIVE.value,
                    "restarted": restarted,
                }

    def get_checkout_details(self, session_id: str) -> dict[str, str | None]:
        with self._session_factory() as db:
            row = db.get(OrderSession, session_id)
            if not row:
                return {"payment_method": "cod", "customer_phone": None}
            return {
                "payment_method": row.payment_method or "cod",
                "customer_phone": row.customer_phone,
            }

    def set_checkout_details(
        self,
        session_id: str,
        *,
        payment_method: str | None = None,
        customer_phone: str | None = None,
    ) -> dict[str, str | None]:
        self.ensure_session(session_id, restart_if_finalized=True)
        with _get_session_lock(session_id):
            with self._session_factory() as db:
                row = db.get(OrderSession, session_id)
                if not row:
                    raise ValueError(f"Session {session_id} not found")
                if payment_method is not None:
                    row.payment_method = payment_method.lower().strip() or "cod"
                if customer_phone is not None:
                    phone = customer_phone.strip()
                    row.customer_phone = phone if phone else None
                row.version = (row.version or 1) + 1
                row.updated_at = datetime.now(timezone.utc)
                db.commit()
                return {
                    "payment_method": row.payment_method or "cod",
                    "customer_phone": row.customer_phone,
                }

    def load_cart(self, session_id: str) -> Cart:
        cart, _ = self.load_cart_with_version(session_id)
        return cart

    def load_cart_with_version(self, session_id: str) -> tuple[Cart, int]:
        self.ensure_session(session_id)
        cart = Cart()
        with self._session_factory() as db:
            session_row = db.get(OrderSession, session_id)
            current_version = session_row.version if session_row else 1
            rows = db.scalars(
                select(CartItemRow)
                .where(CartItemRow.session_id == session_id)
                .order_by(CartItemRow.created_at)
            ).all()
            for row in rows:
                cart._items.append(_row_to_line(row))  # noqa: SLF001
        return cart, current_version

    def save_cart(self, session_id: str, cart: Cart, expected_version: int | None = None) -> int:
        """Persist full cart with optimistic locking check to prevent lost updates."""
        self.ensure_session(session_id)
        with _get_session_lock(session_id):
            with self._session_factory() as db:
                session_row = db.get(OrderSession, session_id)
                if not session_row:
                    raise ValueError(f"Session {session_id} not found")
                if session_row.status != SessionStatus.ACTIVE.value:
                    raise ValueError(f"Session {session_id} is not active (status={session_row.status})")

                if expected_version is not None and session_row.version != expected_version:
                    raise ConcurrentUpdateError(
                        f"Session {session_id} was modified by another request "
                        f"(current version {session_row.version} != expected {expected_version})"
                    )

                existing = db.scalars(
                    select(CartItemRow).where(CartItemRow.session_id == session_id)
                ).all()
                for row in existing:
                    db.delete(row)
                for line in cart.get_items():
                    db.add(_line_to_row(session_id, line))

                session_row.version = (session_row.version or 1) + 1
                session_row.updated_at = datetime.now(timezone.utc)
                db.commit()
                return session_row.version

    def add_cart_item(
        self, session_id: str, line: CartLineItem, expected_version: int | None = None
    ) -> tuple[CartLineItem, int]:
        """Atomically append a line item to cart with optimistic locking."""
        self.ensure_session(session_id)
        with _get_session_lock(session_id):
            with self._session_factory() as db:
                session_row = db.get(OrderSession, session_id)
                if not session_row:
                    raise ValueError(f"Session {session_id} not found")
                if session_row.status != SessionStatus.ACTIVE.value:
                    raise ValueError(f"Session {session_id} is not active (status={session_row.status})")

                if expected_version is not None and session_row.version != expected_version:
                    raise ConcurrentUpdateError(
                        f"Session {session_id} was modified concurrently "
                        f"(version {session_row.version} != expected {expected_version})"
                    )

                item_row = _line_to_row(session_id, line)
                db.add(item_row)
                session_row.version = (session_row.version or 1) + 1
                session_row.updated_at = datetime.now(timezone.utc)
                db.commit()
                return line, session_row.version

    def remove_cart_item(
        self, session_id: str, cart_item_id: str, expected_version: int | None = None
    ) -> tuple[bool, int]:
        """Atomically remove a line item from cart with optimistic locking."""
        self.ensure_session(session_id)
        with _get_session_lock(session_id):
            with self._session_factory() as db:
                session_row = db.get(OrderSession, session_id)
                if not session_row:
                    raise ValueError(f"Session {session_id} not found")
                if session_row.status != SessionStatus.ACTIVE.value:
                    raise ValueError(f"Session {session_id} is not active (status={session_row.status})")

                if expected_version is not None and session_row.version != expected_version:
                    raise ConcurrentUpdateError(
                        f"Session {session_id} was modified concurrently "
                        f"(version {session_row.version} != expected {expected_version})"
                    )

                item = db.scalar(
                    select(CartItemRow).where(
                        CartItemRow.session_id == session_id,
                        CartItemRow.id == cart_item_id,
                    )
                )
                if not item:
                    return False, session_row.version

                db.delete(item)
                session_row.version = (session_row.version or 1) + 1
                session_row.updated_at = datetime.now(timezone.utc)
                db.commit()
                return True, session_row.version

    def start_call_log(self, session_id: str, room_name: str | None = None) -> CallLog:
        with _get_session_lock(session_id):
            with self._session_factory() as db:
                self.ensure_session(session_id, restart_if_finalized=True)
                existing = db.scalar(select(CallLog).where(CallLog.session_id == session_id))
                if existing and existing.status == "active":
                    return existing
                if existing:
                    db.delete(existing)
                log = CallLog(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    room_name=room_name or session_id,
                    status="active",
                    transcript="[]",
                )
                db.add(log)
                db.commit()
                db.refresh(log)
                return log

    def append_transcript(self, session_id: str, role: str, text: str) -> None:
        with _get_session_lock(session_id):
            with self._session_factory() as db:
                log = db.scalar(select(CallLog).where(CallLog.session_id == session_id))
                if not log:
                    log = CallLog(
                        id=str(uuid.uuid4()),
                        session_id=session_id,
                        room_name=session_id,
                        status="active",
                        transcript="[]",
                    )
                    db.add(log)
                entries = json.loads(log.transcript or "[]")
                entries.append(
                    {"role": role, "text": text, "at": datetime.now(timezone.utc).isoformat()}
                )
                log.transcript = json.dumps(entries)
                db.commit()

    def get_chat_history(self, session_id: str) -> list[dict[str, str]]:
        """User/assistant turns for LLM context (excludes tool internals)."""
        with self._session_factory() as db:
            log = db.scalar(select(CallLog).where(CallLog.session_id == session_id))
            if not log:
                return []
            entries = json.loads(log.transcript or "[]")
            return [
                {"role": e["role"], "content": e["text"]}
                for e in entries
                if e.get("role") in ("user", "assistant") and e.get("text")
            ]

    def end_call_log(self, session_id: str) -> None:
        with _get_session_lock(session_id):
            with self._session_factory() as db:
                log = db.scalar(select(CallLog).where(CallLog.session_id == session_id))
                if log:
                    log.status = "ended"
                    log.ended_at = datetime.now(timezone.utc)
                    db.commit()

    def list_call_logs(self, limit: int = 50) -> list[dict]:
        with self._session_factory() as db:
            rows = db.scalars(
                select(CallLog).order_by(CallLog.started_at.desc()).limit(limit)
            ).all()
            return [
                {
                    "id": r.id,
                    "session_id": r.session_id,
                    "room_name": r.room_name,
                    "status": r.status,
                    "transcript": json.loads(r.transcript or "[]"),
                    "started_at": r.started_at.isoformat(),
                    "ended_at": r.ended_at.isoformat() if r.ended_at else None,
                }
                for r in rows
            ]

    def cleanup_abandoned_sessions(
        self,
        max_age_seconds: int = 86400,
        max_age_hours: float | None = None,
        cancel_only: bool = True,
    ) -> int:
        """Clean up stale abandoned sessions without removing recently active sessions."""
        if max_age_hours is not None:
            max_age_seconds = int(max_age_hours * 3600)
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
        cleaned = 0
        with self._session_factory() as db:
            stale = db.scalars(
                select(OrderSession).where(
                    OrderSession.status == SessionStatus.ACTIVE.value,
                    OrderSession.updated_at < cutoff,
                )
            ).all()

            for s in stale:
                if cancel_only:
                    s.status = SessionStatus.CANCELLED.value
                    s.updated_at = datetime.now(timezone.utc)
                    log = db.scalar(select(CallLog).where(CallLog.session_id == s.id))
                    if log and log.status == "active":
                        log.status = "ended"
                        log.ended_at = datetime.now(timezone.utc)
                else:
                    db.delete(s)
                cleaned += 1

            if cleaned > 0:
                db.commit()
                logger.info("Cleaned up %d abandoned sessions older than %ds", cleaned, max_age_seconds)
        return cleaned

    def get_order_by_idempotency_key(self, idempotency_key: str) -> Order | None:
        """Look up order by unique idempotency key with eager loaded payments."""
        if not idempotency_key:
            return None
        with self._session_factory() as db:
            return db.scalar(
                select(Order)
                .options(selectinload(Order.payments))
                .where(Order.idempotency_key == idempotency_key)
            )

    def finalize_session(
        self,
        session_id: str,
        summary: CartSummary,
        menu: MenuData | None = None,
        payment_method: str = "cod",
        customer_phone: str | None = None,
        idempotency_key: str | None = None,
    ) -> Order:
        """Idempotently finalize an active session with strict transactional boundaries.

        Durable database persistence happens BEFORE any external side effects (ticket file,
        POS, payment, SMS). Success is reported only when database commit succeeds.
        """
        if summary.item_count == 0:
            raise ValueError("Cart is empty — cannot finalize an empty order.")

        menu_data = menu or {}
        subtotal = (
            sum(item.line_total_cents * item.quantity for item in summary.items)
            if summary.items
            else summary.total_cents
        )
        totals = calculate_order_totals(subtotal, menu_data)

        idem_key = idempotency_key or f"session-{session_id}"
        payload_hash = _compute_payload_hash(
            session_id, totals["total_cents"], summary.currency, summary, payment_method, customer_phone
        )

        with _get_session_lock(session_id):
            try:
                # Phase 1: Check idempotency & active state in database
                with self._session_factory() as db:
                    existing_order = db.scalar(
                        select(Order).where(Order.idempotency_key == idem_key)
                    )
                    if existing_order:
                        if existing_order.payload_hash == payload_hash:
                            logger.info(
                                "Idempotent replay: key '%s' matched order %s", idem_key, existing_order.id
                            )
                            return existing_order
                        raise IdempotencyConflictError(
                            f"Idempotency conflict: key '{idem_key}' was previously used with a different order payload."
                        )

                    session_row = db.get(OrderSession, session_id)
                    if session_row is None:
                        raise ValueError(f"Session {session_id} not found")
                    if session_row.status == SessionStatus.FINALIZED.value:
                        # Check if session order exists with matching payload
                        existing_session_order = db.scalar(
                            select(Order).where(Order.session_id == session_id)
                        )
                        if existing_session_order and existing_session_order.payload_hash == payload_hash:
                            return existing_session_order
                        raise ValueError(f"Session {session_id} is already finalized.")
                    if session_row.status != SessionStatus.ACTIVE.value:
                        raise ValueError(f"Session {session_id} is not active (status={session_row.status})")

                # Run post-call QA judge (pure computation, no side effects)
                menu_ids = [i["id"] for i in menu_data.get("items", [])]
                judge = run_post_call_judge("pending", summary.spoken_summary, menu_ids)

                # Phase 2: DURABLE DATABASE PERSISTENCE TRANSACTION
                # If this block fails, NO external tickets or external payments are created.
                order_id = str(uuid.uuid4())
                with self._session_factory() as db:
                    s_row = db.get(OrderSession, session_id)
                    if not s_row or s_row.status != SessionStatus.ACTIVE.value:
                        raise ValueError(f"Session {session_id} is no longer active.")

                    order = Order(
                        id=order_id,
                        session_id=session_id,
                        total_cents=totals["total_cents"],
                        currency=summary.currency,
                        item_count=summary.item_count,
                        spoken_summary=summary.spoken_summary,
                        judge_passed=judge.get("passed", True),
                        judge_notes=judge.get("notes"),
                        idempotency_key=idem_key,
                        payload_hash=payload_hash,
                    )
                    s_row.status = SessionStatus.FINALIZED.value
                    s_row.finalized_at = datetime.now(timezone.utc)
                    s_row.version = (s_row.version or 1) + 1
                    s_row.updated_at = datetime.now(timezone.utc)

                    # Initial durable records inside primary transaction
                    kitchen_ticket = KitchenTicket(
                        id=str(uuid.uuid4()),
                        order_id=order.id,
                        ticket_json=json.dumps(
                            {"order_id": order.id, "session_id": session_id, "totals": totals, "item_count": summary.item_count}
                        ),
                        file_path=None,
                        status="queued",
                    )
                    pos = PosSubmission(
                        id=str(uuid.uuid4()),
                        order_id=order.id,
                        provider="mock",
                        external_id=None,
                        status="pending",
                        response_json="{}",
                    )
                    payment = Payment(
                        id=str(uuid.uuid4()),
                        order_id=order.id,
                        method=payment_method,
                        amount_cents=totals["total_cents"],
                        currency=summary.currency,
                        status="pending",
                        external_id=None,
                        response_json="{}",
                    )

                    db.add(order)
                    db.flush()
                    db.add(kitchen_ticket)
                    db.add(pos)
                    db.add(payment)
                    db.commit()
                    db.refresh(order)
            except (ValueError, IdempotencyConflictError):
                raise
            except Exception as exc:
                logger.error("Durable persistence failed for order on session %s: %s", session_id, exc)
                raise OrderIntegrityError(f"Durable database persistence failed: {exc}") from exc

            # Phase 3: POST-PERSISTENCE EXTERNAL EFFECTS (Only executes AFTER DB commit succeeds)
            # 1. Kitchen ticket file
            try:
                ticket_data = write_kitchen_ticket(order.id, session_id, summary)
                ticket_data["totals"] = totals
                with self._session_factory() as db:
                    kt = db.scalar(select(KitchenTicket).where(KitchenTicket.order_id == order.id))
                    if kt:
                        kt.ticket_json = json.dumps(ticket_data)
                        kt.file_path = ticket_data.get("file_path")
                        db.commit()
            except Exception as exc:
                logger.error("Failed to write kitchen ticket file for order %s: %s", order.id, exc)

            # 2. POS submission
            try:
                pos_result = submit_to_pos(
                    order.id, summary, menu_data.get("restaurant", {}).get("id", "dialog-pizza")
                )
                with self._session_factory() as db:
                    p_row = db.scalar(select(PosSubmission).where(PosSubmission.order_id == order.id))
                    if p_row:
                        p_row.provider = pos_result.get("provider", "mock")
                        p_row.external_id = pos_result.get("external_id")
                        p_row.status = pos_result.get("status", "submitted")
                        p_row.response_json = json.dumps(pos_result)
                        db.commit()
            except Exception as exc:
                logger.error("POS submission failed for order %s: %s", order.id, exc)

            # 3. Payment creation
            payment_res: dict = {}
            try:
                payment_res = create_payment(
                    order.id, totals["total_cents"], summary.currency, payment_method, customer_phone
                )
                with self._session_factory() as db:
                    pay_row = db.scalar(select(Payment).where(Payment.order_id == order.id))
                    if pay_row:
                        pay_row.status = payment_res.get("status", "pending")
                        pay_row.external_id = payment_res.get("razorpay_order_id") or payment_res.get("external_id")
                        pay_row.response_json = json.dumps(payment_res)
                        db.commit()
            except Exception as exc:
                logger.error("Payment initialization failed for order %s: %s", order.id, exc)

            # 4. Notifications & SMS
            try:
                notify_order_finalized(order.id, session_id, summary, payment_res)
                send_order_sms(order.id, summary, customer_phone)
            except Exception as exc:
                logger.error("Notification dispatch failed for order %s: %s", order.id, exc)

            # 5. Decrement inventory stock
            try:
                decrement_stock([item.menu_item_id for item in summary.items])
            except Exception as exc:
                logger.warning("Stock decrement failed for order %s: %s", order.id, exc)

            # 6. End call log
            try:
                self.end_call_log(session_id)
            except Exception as exc:
                logger.error("Failed to end call log for session %s: %s", session_id, exc)

            return order

    def list_active_sessions(self) -> list[dict]:
        with self._session_factory() as db:
            rows = db.scalars(
                select(OrderSession)
                .where(OrderSession.status == SessionStatus.ACTIVE.value)
                .order_by(OrderSession.updated_at.desc())
            ).all()
            return [
                {
                    "id": r.id,
                    "status": r.status,
                    "version": r.version,
                    "updated_at": r.updated_at.isoformat(),
                    "item_count": len(r.cart_items),
                }
                for r in rows
            ]

    def list_orders(self, limit: int = 50) -> list[dict]:
        with self._session_factory() as db:
            rows = db.scalars(
                select(Order).order_by(Order.created_at.desc()).limit(limit)
            ).all()
            results = []
            for r in rows:
                payment = db.scalar(select(Payment).where(Payment.order_id == r.id))
                kitchen = db.scalar(select(KitchenTicket).where(KitchenTicket.order_id == r.id))
                pos = db.scalar(select(PosSubmission).where(PosSubmission.order_id == r.id))
                results.append(
                    {
                        "id": r.id,
                        "session_id": r.session_id,
                        "total_cents": r.total_cents,
                        "currency": r.currency,
                        "item_count": r.item_count,
                        "spoken_summary": r.spoken_summary,
                        "judge_passed": r.judge_passed,
                        "judge_notes": r.judge_notes,
                        "idempotency_key": r.idempotency_key,
                        "created_at": r.created_at.isoformat(),
                        "payment_method": payment.method if payment else None,
                        "payment_status": payment.status if payment else None,
                        "kitchen_status": kitchen.status if kitchen else None,
                        "pos_provider": pos.provider if pos else None,
                        "pos_external_id": pos.external_id if pos else None,
                    }
                )
            return results

    def list_kitchen_tickets(self, status: str | None = None, limit: int = 50) -> list[dict]:
        with self._session_factory() as db:
            q = select(KitchenTicket).order_by(KitchenTicket.created_at.desc()).limit(limit)
            rows = db.scalars(q).all()
            tickets = []
            for kt in rows:
                if status and kt.status != status:
                    continue
                order = db.get(Order, kt.order_id)
                data = json.loads(kt.ticket_json or "{}")
                tickets.append(
                    {
                        "id": kt.id,
                        "order_id": kt.order_id,
                        "status": kt.status,
                        "item_count": data.get("item_count", 0),
                        "items": data.get("items", []),
                        "total_cents": order.total_cents if order else data.get("total_cents", 0),
                        "created_at": kt.created_at.isoformat(),
                        "updated_at": kt.updated_at.isoformat() if kt.updated_at else None,
                    }
                )
            return tickets

    def update_kitchen_ticket(self, ticket_id: str, status: str) -> dict:
        valid = {"queued", "preparing", "ready", "served", "cancelled"}
        if status not in valid:
            raise ValueError(f"Invalid status. Use one of: {', '.join(sorted(valid))}")
        with self._session_factory() as db:
            kt = db.get(KitchenTicket, ticket_id)
            if not kt:
                raise ValueError(f"Ticket {ticket_id} not found")
            kt.status = status
            kt.updated_at = datetime.now(timezone.utc)
            db.commit()
            return {"id": kt.id, "order_id": kt.order_id, "status": kt.status}

    def update_payment_status(self, payment_id: str, status: str = "paid") -> dict:
        """Update payment status in DB and persist (F13 fix)."""
        with self._session_factory() as db:
            p = db.get(Payment, payment_id)
            if not p:
                p = db.scalar(
                    select(Payment).where((Payment.order_id == payment_id) | (Payment.external_id == payment_id))
                )
            if not p:
                raise ValueError(f"Payment {payment_id} not found")
            p.status = status
            db.commit()
            return {
                "id": p.id,
                "order_id": p.order_id,
                "status": p.status,
                "method": p.method,
                "amount_cents": p.amount_cents,
                "currency": p.currency,
            }

    def list_pos_submissions(self, limit: int = 20) -> dict:
        with self._session_factory() as db:
            rows = db.scalars(
                select(PosSubmission).order_by(PosSubmission.created_at.desc()).limit(limit)
            ).all()
            return [
                {
                    "id": r.id,
                    "order_id": r.order_id,
                    "provider": r.provider,
                    "external_id": r.external_id,
                    "status": r.status,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ]

    def get_session_cart_summary(self, session_id: str, menu: MenuData) -> CartSummary | None:
        cart = self.load_cart(session_id)
        if cart.is_empty():
            return cart.summarize(menu)
        return cart.summarize(menu)


_default_repo: CartRepository | None = None


def get_cart_repository(url: str | None = None) -> CartRepository:
    global _default_repo
    if _default_repo is None:
        engine = create_db_engine(url)
        init_db(engine)
        _default_repo = CartRepository(sessionmaker(bind=engine, expire_on_commit=False))
    return _default_repo


def reset_cart_repository() -> None:
    global _default_repo
    _default_repo = None
