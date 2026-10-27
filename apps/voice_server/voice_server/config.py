"""Free-tier provider configuration for the voice pipeline.

Default stack (all free tier, lowest latency):
  STT  → Deepgram nova-3 (streaming, $200 free credit)
  LLM  → Groq gpt-oss-20b (~1000 tok/s, tool calling)
  TTS  → Deepgram Aura-2 (streaming, same free credit)
  VAD  → Silero (local, free)
  RTC  → LiveKit Cloud (free tier)
"""

from __future__ import annotations

import os

# Import on module load so LiveKit registers plugins on the main thread.
from livekit.plugins import deepgram, openai  # noqa: F401

from menu_engine.utils.groq_client import get_groq_voice_model


def _truthy(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes")


def get_llm():
    """Groq free tier — fastest model with tool calling (gpt-oss-20b)."""
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        raise RuntimeError(
            "Set GROQ_API_KEY (free at console.groq.com) for voice LLM"
        )
    return openai.LLM(
        model=get_groq_voice_model(),
        base_url="https://api.groq.com/openai/v1",
        api_key=groq_key,
        temperature=float(os.getenv("GROQ_VOICE_TEMPERATURE", "0.2")),
    )


def get_stt():
    """Deepgram free tier — low-latency streaming STT."""
    if not os.getenv("DEEPGRAM_API_KEY"):
        raise RuntimeError(
            "Set DEEPGRAM_API_KEY (free $200 credit at console.deepgram.com)"
        )
    return deepgram.STT(
        model=os.getenv("DEEPGRAM_MODEL", "nova-3"),
        interim_results=True,
        smart_format=True,
        endpointing_ms=int(os.getenv("DEEPGRAM_ENDPOINTING_MS", "150")),
    )


def get_tts():
    """Free-tier TTS: Deepgram Aura streaming (fast) → Edge TTS (slow fallback)."""
    if _truthy("VOICE_ALLOW_PAID"):
        if os.getenv("CARTESIA_API_KEY"):
            from livekit.plugins import cartesia

            return cartesia.TTS(
                model=os.getenv("CARTESIA_TTS_MODEL", "sonic-turbo"),
            )
        if os.getenv("ELEVENLABS_API_KEY"):
            from livekit.plugins import elevenlabs

            return elevenlabs.TTS()

    if os.getenv("DEEPGRAM_API_KEY") and not _truthy("USE_EDGE_TTS"):
        return deepgram.TTS(
            model=os.getenv("DEEPGRAM_TTS_MODEL", "aura-2-andromeda-en"),
        )

    from voice_server.tts.edge_tts import EdgeTTS

    return EdgeTTS(voice=os.getenv("EDGE_TTS_VOICE", "en-US-AriaNeural"))


def get_turn_handling() -> dict:
    """Conversation pacing — start LLM/TTS early, end turns quickly."""
    return {
        "endpointing": {
            "min_delay": float(os.getenv("VOICE_ENDPOINT_MIN_DELAY", "0.15")),
            "max_delay": float(os.getenv("VOICE_ENDPOINT_MAX_DELAY", "0.9")),
        },
        "interruption": {"enabled": True, "min_duration": 0.2},
        "preemptive_generation": {
            "enabled": _truthy("VOICE_PREEMPTIVE", "true"),
            "preemptive_tts": _truthy("VOICE_PREEMPTIVE_TTS", "true"),
        },
    }


def describe_voice_stack() -> str:
    """Human-readable summary of the active free-tier voice providers."""
    llm = get_groq_voice_model()
    stt = os.getenv("DEEPGRAM_MODEL", "nova-3")
    if _truthy("USE_EDGE_TTS"):
        tts = f"Edge TTS ({os.getenv('EDGE_TTS_VOICE', 'en-US-AriaNeural')})"
    elif _truthy("VOICE_ALLOW_PAID") and os.getenv("CARTESIA_API_KEY"):
        tts = os.getenv("CARTESIA_TTS_MODEL", "sonic-turbo")
    elif _truthy("VOICE_ALLOW_PAID") and os.getenv("ELEVENLABS_API_KEY"):
        tts = "ElevenLabs"
    else:
        tts = os.getenv("DEEPGRAM_TTS_MODEL", "aura-2-andromeda-en")
    return f"LLM=Groq/{llm} | STT=Deepgram/{stt} | TTS={tts} | VAD=Silero (local)"


def get_livekit_config() -> dict:
    return {
        "url": os.getenv("LIVEKIT_URL", ""),
        "api_key": os.getenv("LIVEKIT_API_KEY", ""),
        "api_secret": os.getenv("LIVEKIT_API_SECRET", ""),
    }
