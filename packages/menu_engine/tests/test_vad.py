"""Verify Silero VAD loads for voice agent."""

from __future__ import annotations


def test_silero_vad_loads():
    from livekit.plugins import silero

    vad = silero.VAD.load(
        min_speech_duration=0.05,
        min_silence_duration=0.4,
        activation_threshold=0.5,
    )
    assert vad is not None
