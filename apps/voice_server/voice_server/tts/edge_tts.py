"""Free TTS via Microsoft Edge (no API key required). Streams MP3 → PCM for lower latency."""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass

import edge_tts
from livekit.agents import tts
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions

from voice_server.utils.ffmpeg_setup import find_ffmpeg

_PCM_CHUNK = 4096


@dataclass
class _EdgeOptions:
    voice: str


class EdgeTTS(tts.TTS):
    def __init__(self, voice: str = "en-US-AriaNeural") -> None:
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=True),
            sample_rate=24000,
            num_channels=1,
        )
        self._opts = _EdgeOptions(voice=voice)

    def synthesize(
        self,
        text: str,
        *,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> tts.ChunkedStream:
        return _EdgeChunkedStream(
            tts=self,
            text=text,
            opts=self._opts,
            conn_options=conn_options,
        )


class _EdgeChunkedStream(tts.ChunkedStream):
    def __init__(
        self,
        *,
        tts: EdgeTTS,
        text: str,
        opts: _EdgeOptions,
        conn_options: APIConnectOptions,
    ) -> None:
        super().__init__(tts=tts, input_text=text, conn_options=conn_options)
        self._opts = opts

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            raise RuntimeError(
                "ffmpeg not found — install with: winget install Gyan.FFmpeg"
            )

        output_emitter.initialize(
            request_id="edge-tts",
            sample_rate=24000,
            num_channels=1,
            mime_type="audio/pcm",
        )

        proc = await asyncio.create_subprocess_exec(
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "24000",
            "-ac",
            "1",
            "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        communicate = edge_tts.Communicate(self._input_text, self._opts.voice)

        async def _feed_mp3() -> None:
            assert proc.stdin is not None
            try:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        proc.stdin.write(chunk["data"])
                        await proc.stdin.drain()
            finally:
                proc.stdin.close()

        async def _read_pcm() -> None:
            assert proc.stdout is not None
            while True:
                data = await proc.stdout.read(_PCM_CHUNK)
                if not data:
                    break
                output_emitter.push(data)

        feed_task = asyncio.create_task(_feed_mp3())
        read_task = asyncio.create_task(_read_pcm())
        await asyncio.gather(feed_task, read_task)

        if proc.returncode is None:
            await proc.wait()
        if proc.returncode not in (0, None):
            err = b""
            if proc.stderr:
                err = await proc.stderr.read()
            raise RuntimeError(
                f"ffmpeg MP3 decode failed: {err.decode(errors='replace')[-500:]}"
            )

        output_emitter.flush()


def _mp3_to_pcm(mp3_bytes: bytes) -> bytes:
    """Sync fallback used by tests."""
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError(
            "ffmpeg not found — install with: winget install Gyan.FFmpeg"
        )

    proc = subprocess.run(
        [
            ffmpeg,
            "-i",
            "pipe:0",
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "24000",
            "-ac",
            "1",
            "pipe:1",
        ],
        input=mp3_bytes,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode(errors="replace")[-500:]
        raise RuntimeError(f"ffmpeg MP3 decode failed: {err}")
    return proc.stdout
