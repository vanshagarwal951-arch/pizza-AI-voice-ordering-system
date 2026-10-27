"""Database backup and recovery utilities.

Provides safe online backups for SQLite without taking the database offline,
and recovery/verification helpers.
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def backup_sqlite_database(
    source_path: Path | str,
    backup_dir: Path | str | None = None,
    prefix: str = "voice_ordering_backup",
) -> Path:
    """Create a consistent online backup of a SQLite database using the SQLite backup API.

    This avoids locking the database or creating corrupted copies during active writes.
    """
    src = Path(source_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Database file not found: {src}")

    b_dir = Path(backup_dir) if backup_dir else src.parent / "backups"
    b_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = b_dir / f"{prefix}_{timestamp}.db"

    # Open source in read-only URI mode and destination in write mode
    src_conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    dest_conn = sqlite3.connect(dest)

    try:
        # Use SQLite online backup API to copy pages safely
        with dest_conn:
            src_conn.backup(dest_conn, pages=100)
        logger.info("Successfully created SQLite backup at %s", dest)
    finally:
        dest_conn.close()
        src_conn.close()

    return dest


def verify_database_integrity(db_path: Path | str) -> bool:
    """Run SQLite integrity_check PRAGMA to verify database is not corrupted."""
    path = Path(db_path).resolve()
    if not path.exists():
        return False
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        result = cursor.fetchone()
        conn.close()
        return bool(result and result[0] == "ok")
    except Exception as exc:
        logger.error("Database integrity check failed for %s: %s", path, exc)
        return False
