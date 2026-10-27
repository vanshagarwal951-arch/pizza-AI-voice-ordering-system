"""Voice pipeline: free-tier providers with lowest latency defaults."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _clear_voice_env(monkeypatch):
    for key in (
        "GROQ_VOICE_MODEL",
        "USE_EDGE_TTS",
        "VOICE_ALLOW_PAID",
        "CARTESIA_API_KEY",
        "DEEPGRAM_API_KEY",
        "ELEVENLABS_API_KEY",
        "VOICE_PREEMPTIVE",
        "VOICE_PREEMPTIVE_TTS",
    ):
        monkeypatch.delenv(key, raising=False)


def test_voice_model_defaults_to_fastest_free_groq():
    from menu_engine.utils.groq_client import (
        DEFAULT_GROQ_VOICE_MODEL,
        get_groq_voice_model,
    )

    assert get_groq_voice_model() == DEFAULT_GROQ_VOICE_MODEL
    assert DEFAULT_GROQ_VOICE_MODEL == "openai/gpt-oss-20b"


def test_tts_uses_deepgram_aura_by_default(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "test-key")

    from voice_server.config import get_tts

    with patch("livekit.plugins.deepgram.TTS") as mock_tts:
        get_tts()
        mock_tts.assert_called_once_with(model="aura-2-andromeda-en")


def test_tts_ignores_paid_providers_without_opt_in(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "test-key")
    monkeypatch.setenv("CARTESIA_API_KEY", "paid-key")

    from voice_server.config import get_tts

    with patch("livekit.plugins.deepgram.TTS") as mock_tts:
        get_tts()
        mock_tts.assert_called_once()


def test_tts_edge_fallback_when_requested(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "test-key")
    monkeypatch.setenv("USE_EDGE_TTS", "true")

    from voice_server.config import get_tts

    with patch("voice_server.tts.edge_tts.EdgeTTS") as mock_edge:
        get_tts()
        mock_edge.assert_called_once()


def test_stt_low_latency_defaults(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "test-key")

    from voice_server.config import get_stt

    with patch("livekit.plugins.deepgram.STT") as mock_stt:
        get_stt()
        _, kwargs = mock_stt.call_args
        assert "utterance_end_ms" not in kwargs
        assert kwargs["model"] == "nova-3"
        assert kwargs["endpointing_ms"] == 150


def test_turn_handling_enables_preemptive_tts():
    from voice_server.config import get_turn_handling

    th = get_turn_handling()
    assert th["preemptive_generation"]["enabled"] is True
    assert th["preemptive_generation"]["preemptive_tts"] is True
    assert th["endpointing"]["min_delay"] == 0.15


def test_describe_voice_stack(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "test-key")

    from voice_server.config import describe_voice_stack

    summary = describe_voice_stack()
    assert "Groq/openai/gpt-oss-20b" in summary
    assert "Deepgram/nova-3" in summary
    assert "aura-2-andromeda-en" in summary
