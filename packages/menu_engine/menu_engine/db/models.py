from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "data" / "voice_ordering.db"


class DatabaseConnectionError(RuntimeError):
    """Raised when configured database connection fails."""


def sanitize_database_url(url: str) -> str:
    """Mask credentials in database URL to prevent credential leakage in logs/errors."""
    if not url:
        return ""
    return re.sub(r"://([^:@]+):([^@]+)@", r"://\1:***@", url)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):
    """Enforce foreign keys, WAL mode, and busy timeout for SQLite connections."""
    import sqlite3

    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("PRAGMA journal_mode = WAL;")
        cursor.execute("PRAGMA busy_timeout = 30000;")  # 30-second timeout on locked database
        cursor.execute("PRAGMA synchronous = NORMAL;")
        cursor.close()


class Base(DeclarativeBase):
    pass


class SessionStatus(str, Enum):
    ACTIVE = "active"
    FINALIZED = "finalized"
    CANCELLED = "cancelled"


class OrderSession(Base):
    __tablename__ = "order_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default=SessionStatus.ACTIVE.value)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(20), nullable=True, default="cod")
    customer_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)

    cart_items: Mapped[list["CartItemRow"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    order: Mapped["Order | None"] = relationship(back_populates="session", uselist=False)
    call_log: Mapped["CallLog | None"] = relationship(back_populates="session", uselist=False)


class CartItemRow(Base):
    __tablename__ = "cart_items"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("order_sessions.id", ondelete="CASCADE"))
    menu_item_id: Mapped[str] = mapped_column(String)
    menu_item_name: Mapped[str] = mapped_column(String)
    size_id: Mapped[str] = mapped_column(String)
    size_name: Mapped[str] = mapped_column(String)
    is_half_and_half: Mapped[bool] = mapped_column(default=False)
    left_toppings: Mapped[str] = mapped_column(Text, default="[]")
    right_toppings: Mapped[str] = mapped_column(Text, default="[]")
    whole_toppings: Mapped[str] = mapped_column(Text, default="[]")
    crust_id: Mapped[str | None] = mapped_column(String, nullable=True)
    line_total_cents: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped[OrderSession] = relationship(back_populates="cart_items")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("order_sessions.id"), unique=True)
    total_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    item_count: Mapped[int] = mapped_column(Integer)
    spoken_summary: Mapped[str] = mapped_column(Text)
    judge_passed: Mapped[bool | None] = mapped_column(default=None)
    judge_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128), unique=True, nullable=True, index=True
    )
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped[OrderSession] = relationship(back_populates="order")
    kitchen_ticket: Mapped["KitchenTicket | None"] = relationship(
        back_populates="order", uselist=False
    )
    payments: Mapped[list["Payment"]] = relationship(back_populates="order")
    pos_submissions: Mapped[list["PosSubmission"]] = relationship(back_populates="order")


class CallLog(Base):
    __tablename__ = "call_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("order_sessions.id"), unique=True)
    room_name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String(20), default="active")
    transcript: Mapped[str] = mapped_column(Text, default="[]")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped[OrderSession] = relationship(back_populates="call_log")


class KitchenTicket(Base):
    __tablename__ = "kitchen_tickets"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), unique=True)
    ticket_json: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    order: Mapped[Order] = relationship(back_populates="kitchen_ticket")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    method: Mapped[str] = mapped_column(String(20), default="cod")
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)
    response_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    order: Mapped[Order] = relationship(back_populates="payments")


class PosSubmission(Base):
    __tablename__ = "pos_submissions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    provider: Mapped[str] = mapped_column(String(50), default="mock")
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="submitted")
    response_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    order: Mapped[Order] = relationship(back_populates="pos_submissions")


def get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url
    DEFAULT_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+pysqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"


def create_db_engine(url: str | None = None):
    db_url = url or get_database_url()
    connect_args = {}
    engine_kwargs = {"pool_pre_ping": True}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        connect_args["timeout"] = 30.0  # Wait up to 30s for locks
        engine_kwargs["connect_args"] = connect_args
    elif "postgresql" in db_url:
        engine_kwargs["pool_size"] = int(os.getenv("DB_POOL_SIZE", "10"))
        engine_kwargs["max_overflow"] = int(os.getenv("DB_MAX_OVERFLOW", "20"))
        engine_kwargs["pool_recycle"] = 1800
    return create_engine(db_url, **engine_kwargs)


def ping_database(engine=None, timeout: float = 3.0) -> bool:
    """Check database connectivity with a lightweight query."""
    eng = engine or create_db_engine()
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
            return True
    except Exception as exc:
        sanitized = sanitize_database_url(str(eng.url))
        logger.error("Database ping failed for %s: %s", sanitized, exc)
        return False


_ALLOWED_SQLITE_TABLES = {
    "kitchen_tickets",
    "order_sessions",
    "cart_items",
    "orders",
    "call_logs",
    "payments",
    "pos_submissions",
}


def _sqlite_has_column(conn, table: str, column: str) -> bool:
    """Check if SQLite table has column, validating table name to prevent SQL injection (F12 fix)."""
    if table not in _ALLOWED_SQLITE_TABLES:
        raise ValueError(f"Disallowed table name in schema migration: {table}")
    rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def migrate_schema(engine=None) -> None:
    """Lightweight SQLite upgrades for dev databases."""
    eng = engine or create_db_engine()
    if not str(eng.url).startswith("sqlite"):
        return
    with eng.begin() as conn:
        if not _sqlite_has_column(conn, "kitchen_tickets", "status"):
            conn.exec_driver_sql(
                "ALTER TABLE kitchen_tickets ADD COLUMN status VARCHAR(20) DEFAULT 'queued'"
            )
        if not _sqlite_has_column(conn, "kitchen_tickets", "updated_at"):
            conn.exec_driver_sql(
                "ALTER TABLE kitchen_tickets ADD COLUMN updated_at DATETIME"
            )
        if not _sqlite_has_column(conn, "order_sessions", "payment_method"):
            conn.exec_driver_sql(
                "ALTER TABLE order_sessions ADD COLUMN payment_method VARCHAR(20) DEFAULT 'cod'"
            )
        if not _sqlite_has_column(conn, "order_sessions", "customer_phone"):
            conn.exec_driver_sql(
                "ALTER TABLE order_sessions ADD COLUMN customer_phone VARCHAR(32)"
            )
        if not _sqlite_has_column(conn, "order_sessions", "version"):
            conn.exec_driver_sql(
                "ALTER TABLE order_sessions ADD COLUMN version INTEGER DEFAULT 1 NOT NULL"
            )
        if not _sqlite_has_column(conn, "orders", "idempotency_key"):
            conn.exec_driver_sql(
                "ALTER TABLE orders ADD COLUMN idempotency_key VARCHAR(128)"
            )
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_idempotency_key ON orders(idempotency_key)"
            )
        if not _sqlite_has_column(conn, "orders", "payload_hash"):
            conn.exec_driver_sql(
                "ALTER TABLE orders ADD COLUMN payload_hash VARCHAR(64)"
            )


def init_db(engine=None) -> None:
    eng = engine or create_db_engine()
    if os.getenv("DATABASE_URL"):
        if not ping_database(eng):
            sanitized = sanitize_database_url(str(eng.url))
            raise DatabaseConnectionError(
                f"Configured primary database at '{sanitized}' is unreachable. "
                "Refusing to silently switch to a fallback database."
            )
    Base.metadata.create_all(eng)
    migrate_schema(eng)
