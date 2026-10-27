"""Small shared helpers."""

from __future__ import annotations

import sys


def configure_utf8_stdio() -> None:
    """Avoid Windows charmap errors when logging INR symbols."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def safe_print(text: str) -> None:
    configure_utf8_stdio()
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(text.encode(encoding, errors="replace").decode(encoding, errors="replace"), flush=True)
