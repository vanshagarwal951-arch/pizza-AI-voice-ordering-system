"""Locate ffmpeg on Windows (including WinGet installs) and add it to PATH."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def find_ffmpeg() -> str | None:
    explicit = os.getenv("FFMPEG_PATH", "").strip().strip('"')
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return str(p)
        if p.is_dir() and (p / "ffmpeg.exe").is_file():
            return str(p / "ffmpeg.exe")

    found = shutil.which("ffmpeg")
    if found:
        return found

    local = os.environ.get("LOCALAPPDATA", "")
    candidates: list[Path] = [
        Path(local) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe",
    ]

    packages = Path(local) / "Microsoft" / "WinGet" / "Packages"
    if packages.is_dir():
        for pkg in sorted(packages.glob("Gyan.FFmpeg*"), reverse=True):
            for ffmpeg in pkg.glob("**/bin/ffmpeg.exe"):
                candidates.append(ffmpeg)

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def configure_ffmpeg() -> str | None:
    """Ensure ffmpeg bin dir is on PATH. Returns ffmpeg.exe path if found."""
    path = find_ffmpeg()
    if not path:
        return None

    bin_dir = str(Path(path).parent)
    if bin_dir.casefold() not in os.environ.get("PATH", "").casefold():
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")

    return path
