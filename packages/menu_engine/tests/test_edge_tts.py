"""Regression tests for custom Edge TTS (LiveKit 1.6+ conn_options API)."""

from __future__ import annotations

import asyncio
import inspect

import pytest

pytest.importorskip("voice_server")

from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
from voice_server.tts.edge_tts import EdgeTTS


def test_edge_tts_synthesize_accepts_conn_options():
    sig = inspect.signature(EdgeTTS.synthesize)
    assert "conn_options" in sig.parameters


def test_edge_tts_produces_audio():
    async def _run() -> None:
        tts = EdgeTTS()
        stream = tts.synthesize("Test audio.", conn_options=DEFAULT_API_CONNECT_OPTIONS)
        frames = [ev.frame async for ev in stream]
        assert frames
        assert sum(len(f.data) for f in frames) > 1000

    asyncio.run(_run())
