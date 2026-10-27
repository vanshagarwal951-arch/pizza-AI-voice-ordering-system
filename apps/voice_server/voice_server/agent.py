from __future__ import annotations

import os
import time
from typing import Annotated, Optional

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    RunContext,
    WorkerOptions,
    cli,
    function_tool,
)
from livekit.plugins import deepgram, openai, silero

from voice_server.config import describe_voice_stack, get_llm, get_stt, get_tts, get_turn_handling
from voice_server.prompts.system import SYSTEM_PROMPT
from voice_server.tools.executor import SessionToolExecutor
from voice_server.utils.ffmpeg_setup import configure_ffmpeg

from voice_server.utils.console import configure_utf8_stdio

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"), override=True)
configure_utf8_stdio()

AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME", "dialog-order-agent")

_ffmpeg = configure_ffmpeg()
if _ffmpeg:
    print(f"ffmpeg configured: {_ffmpeg}")
else:
    print("WARNING: ffmpeg not found - Edge TTS audio may fail. Install: winget install Gyan.FFmpeg")

_executors: dict[str, SessionToolExecutor] = {}
_executor_timestamps: dict[str, float] = {}


def cleanup_stale_executors(max_age_seconds: float = 3600.0) -> int:
    """Evict in-memory executors that haven't been accessed within max_age_seconds."""
    now = time.time()
    stale_keys = [
        sid
        for sid, last_active in _executor_timestamps.items()
        if (now - last_active) > max_age_seconds
    ]
    for sid in stale_keys:
        _executors.pop(sid, None)
        _executor_timestamps.pop(sid, None)
    return len(stale_keys)


def _ids_to_toppings(ids: Optional[list[str]]) -> list[dict]:
    """Convert topping ID lists to menu-engine format (Groq rejects nested object schemas)."""
    if not ids:
        return []
    return [{"modifier_id": topping_id, "extra": False} for topping_id in ids]


def _get_executor(session_id: str) -> SessionToolExecutor:
    cleanup_stale_executors()
    _executor_timestamps[session_id] = time.time()
    if session_id not in _executors:
        _executors[session_id] = SessionToolExecutor(session_id)
    return _executors[session_id]


class DialogOrderAgent(Agent):
    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        super().__init__(instructions=SYSTEM_PROMPT)

    @function_tool()
    async def add_item(
        self,
        context: RunContext,
        item_name: Annotated[
            str,
            "Menu item name as the customer says it, e.g. Margherita, Chicken Tikka Pizza, Cafe Latte",
        ],
        size: Annotated[
            str,
            "Size: regular (burgers/drinks/etc), or small, medium, large for pizzas",
        ] = "regular",
        is_half_and_half: Annotated[bool, "True for half-and-half pizzas"] = False,
        left_toppings: Annotated[
            Optional[list[str]], "Left half topping names, e.g. ['pepperoni']"
        ] = None,
        right_toppings: Annotated[
            Optional[list[str]], "Right half topping names, e.g. ['mushroom']"
        ] = None,
        whole_toppings: Annotated[
            Optional[list[str]], "Whole pizza topping names, e.g. ['pepperoni', 'sausage']"
        ] = None,
        crust_id: Annotated[Optional[str], "Crust option name or id"] = None,
        quantity: Annotated[int, "Quantity"] = 1,
    ) -> str:
        return _get_executor(self._session_id).run(
            "add_item",
            {
                "item_name": item_name,
                "size": size,
                "is_half_and_half": is_half_and_half,
                "left_toppings": _ids_to_toppings(left_toppings),
                "right_toppings": _ids_to_toppings(right_toppings),
                "whole_toppings": _ids_to_toppings(whole_toppings),
                "crust_id": crust_id,
                "quantity": quantity,
            },
        )

    @function_tool()
    async def remove_item(
        self,
        context: RunContext,
        cart_item_id: Annotated[str, "Cart line item ID from add_item"],
    ) -> str:
        return _get_executor(self._session_id).run(
            "remove_item", {"cart_item_id": cart_item_id}
        )

    @function_tool()
    async def read_back_cart(self, context: RunContext) -> str:
        return _get_executor(self._session_id).run("read_back_cart", {})

    @function_tool()
    async def finalize_order(
        self,
        context: RunContext,
        payment_method: Annotated[
            str, "Payment method: cod (cash on delivery), upi, or razorpay"
        ] = "cod",
        customer_phone: Annotated[
            Optional[str], "Customer mobile number for SMS order confirmation, e.g. +919876543210"
        ] = None,
        confirmed: Annotated[
            bool, "Must be True ONLY if customer explicitly confirmed the order summary and total price"
        ] = False,
        idempotency_key: Annotated[
            Optional[str], "Optional unique client request key to prevent duplicate orders"
        ] = None,
    ) -> str:
        return _get_executor(self._session_id).run(
            "finalize_order",
            {
                "payment_method": payment_method,
                "customer_phone": customer_phone,
                "confirmed": confirmed,
                "idempotency_key": idempotency_key,
            },
        )

    @function_tool()
    async def transfer_to_human(self, context: RunContext) -> str:
        return _get_executor(self._session_id).run(
            "transfer_to_human",
            {"reason": "Customer requested staff"},
        )


def prewarm(proc: JobProcess) -> None:
    """Load models/providers on the job process main thread."""
    try:
        vad = silero.VAD.load(
            min_speech_duration=0.05,
            min_silence_duration=0.35,
            activation_threshold=0.5,
        )
    except Exception as exc:
        raise RuntimeError(
            "Silero VAD failed to load - run: pip install livekit-plugins-silero onnxruntime"
        ) from exc
    proc.userdata["vad"] = vad
    proc.userdata["stt"] = get_stt()
    proc.userdata["llm"] = get_llm()
    proc.userdata["tts"] = get_tts()
    print(f"Silero VAD: connected (local voice activity detection)")
    print(f"Voice stack (free tier): {describe_voice_stack()}")


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()
    session_id = ctx.room.name or f"session-{ctx.job.id}"

    async def _cleanup() -> None:
        _executors.pop(session_id, None)
        _executor_timestamps.pop(session_id, None)

    ctx.add_shutdown_callback(_cleanup)

    vad = ctx.proc.userdata.get("vad")
    if vad is None:
        raise RuntimeError("Silero VAD not initialized - prewarm failed")

    session = AgentSession(
        vad=vad,
        stt=ctx.proc.userdata["stt"],
        llm=ctx.proc.userdata["llm"],
        tts=ctx.proc.userdata["tts"],
        turn_handling=get_turn_handling(),
    )

    agent = DialogOrderAgent(session_id=session_id)
    await session.start(agent=agent, room=ctx.room)
    await session.generate_reply(
        instructions=(
            "Say exactly this greeting, word for word: "
            "'Hi! Welcome to DIALOG Pizza. I'm your AI order taker. What would you like to order today?' "
            "Do not mention Tony's Pizza or any other restaurant."
        )
    )


def main() -> None:
    print(f"Voice agent registered as '{AGENT_NAME}' (explicit dispatch — joins on Connect Microphone)")
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            num_idle_processes=1,
            agent_name=AGENT_NAME,
        )
    )


if __name__ == "__main__":
    main()
