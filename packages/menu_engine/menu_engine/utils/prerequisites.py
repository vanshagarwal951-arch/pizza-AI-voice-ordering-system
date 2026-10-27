"""Shared environment and dependency checks for voice mode."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CheckResult:
    name: str
    ok: bool
    message: str
    required: bool = True


@dataclass
class PrerequisiteReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks if c.required)

    def lines(self) -> list[str]:
        out: list[str] = []
        for check in self.checks:
            icon = "OK" if check.ok else ("WARN" if not check.required else "FAIL")
            suffix = "" if check.required else " (optional)"
            out.append(f"[{icon}] {check.name}{suffix}: {check.message}")
        return out


def _env_set(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def _find_ffmpeg() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        candidates = [Path(local) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"]
        packages = Path(local) / "Microsoft" / "WinGet" / "Packages"
        if packages.is_dir():
            for pkg in sorted(packages.glob("Gyan.FFmpeg*"), reverse=True):
                for f in pkg.glob("**/bin/ffmpeg.exe"):
                    candidates.append(f)
        for c in candidates:
            if c.is_file():
                return str(c)
    return None


def check_ffmpeg(required: bool = True) -> CheckResult:
    path = _find_ffmpeg()
    if path:
        try:
            proc = subprocess.run(
                [path, "-version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            version_line = (proc.stdout or proc.stderr).splitlines()[0] if proc.stdout or proc.stderr else path
        except (OSError, subprocess.TimeoutExpired):
            version_line = path
        return CheckResult("ffmpeg", True, version_line, required=required)

    return CheckResult(
        "ffmpeg",
        False,
        "Not found — Edge TTS needs ffmpeg for MP3→PCM. Install: winget install Gyan.FFmpeg",
        required=required,
    )


def check_voice_prerequisites() -> PrerequisiteReport:
    report = PrerequisiteReport()

    for name, label, hint in [
        ("GROQ_API_KEY", "Groq LLM", "https://console.groq.com"),
        ("DEEPGRAM_API_KEY", "Deepgram STT", "https://console.deepgram.com"),
        ("LIVEKIT_URL", "LiveKit URL", "https://cloud.livekit.io"),
        ("LIVEKIT_API_KEY", "LiveKit API key", "https://cloud.livekit.io"),
        ("LIVEKIT_API_SECRET", "LiveKit API secret", "https://cloud.livekit.io"),
    ]:
        ok = _env_set(name)
        report.checks.append(
            CheckResult(
                label,
                ok,
                "configured" if ok else f"missing — set {name} in .env ({hint})",
            )
        )

    use_edge = os.getenv("USE_EDGE_TTS", "false").lower() in ("1", "true", "yes")
    report.checks.append(check_ffmpeg(required=use_edge))

    if use_edge:
        report.checks.append(
            CheckResult(
                "Edge TTS fallback",
                True,
                "enabled — slower than Deepgram Aura; needs ffmpeg",
                required=False,
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "Deepgram TTS",
                _env_set("DEEPGRAM_API_KEY"),
                "Aura streaming (free tier, low latency)",
                required=False,
            )
        )

    return report


def print_prerequisite_report(report: PrerequisiteReport) -> int:
    print("Voice ordering prerequisites\n" + "=" * 40)
    for line in report.lines():
        print(line)
    print("=" * 40)
    if report.passed:
        print("All required checks passed.")
        return 0
    print("Fix the FAIL items above, then re-run.")
    return 1


def main() -> None:
    from dotenv import load_dotenv

    from menu_engine.db.models import PROJECT_ROOT

    load_dotenv(PROJECT_ROOT / ".env", override=True)
    sys.exit(print_prerequisite_report(check_voice_prerequisites()))


if __name__ == "__main__":
    main()
