"""Safe atomic file operations."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_json(file_path: Path, data: Any, indent: int = 2) -> None:
    """Write JSON data to file atomically using a temporary file and atomic replace (F11 fix)."""
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    dir_path = file_path.parent

    # Write to a temporary file in the same directory (same filesystem for atomic rename)
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=f".{file_path.name}.", dir=str(dir_path), text=True)
    try:
        with open(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, file_path)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise
