from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Header, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator

from menu_engine.menu.loader import load_menu, reset_menu_cache
from menu_engine.services.auth import verify_token
from menu_engine import (
    cart_summary_to_dict,
    create_order_tools,
    execute_tool,
    get_cart_repository,
    init_db,
    tool_result_to_dict,
)
from menu_engine.chat.groq_agent import GroqChatAgent
from menu_engine.cart.persistent import PersistentSessionManager
from menu_engine.db.models import create_db_engine, get_database_url, ping_database

from menu_engine.utils.console import configure_utf8_stdio

from web.routes.product import router as product_router
from web.middleware import SecurityHeadersMiddleware, RequestSizeLimitMiddleware

load_dotenv(dotenv_path=Path(__file__).resolve().parents[3] / ".env", override=True)
configure_utf8_stdio()

STATIC_DIR = Path(__file__).resolve().parent / "static"

menu = load_menu()
repo = None


def get_repo():
    global repo
    if repo is None:
        repo = get_cart_repository()
    return repo


@asynccontextmanager
async def lifespan(app: FastAPI):
    global menu, repo
    reset_menu_cache()
    menu = load_menu()
    engine = create_db_engine(get_database_url())
    init_db(engine)
    repo = None
    get_repo()
    yield


app = FastAPI(title="DIALOG Pizza — Voice Ordering Platform", lifespan=lifespan)

# Add CORS middleware (F03 fix)
# For local development, allow localhost origins
# For production, configure specific origins via environment variable
ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
    max_age=600,  # Cache preflight requests for 10 minutes
)

# Add security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# Add request size limit middleware (1MB for JSON payloads)
app.add_middleware(RequestSizeLimitMiddleware, max_size=1024 * 1024)

app.include_router(product_router)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class ToolRequest(BaseModel):
    session_id: str = Field(default="demo-room", max_length=100)
    tool: str = Field(max_length=50)
    args: dict[str, Any] = Field(default_factory=dict)

    @validator("session_id")
    def validate_session_id(cls, v):
        """Validate session ID contains only safe characters."""
        if not v or not v.strip():
            raise ValueError("session_id cannot be empty")
        # Strict validation - reject path traversal attempts
        if ".." in v or "/" in v or "\\" in v:
            raise ValueError("session_id cannot contain path traversal characters")
        # Only allow alphanumeric, hyphens, and underscores
        if not all(c.isalnum() or c in "-_" for c in v):
            raise ValueError("session_id can only contain alphanumeric characters, hyphens, and underscores")
        return v[:100]

    @validator("tool")
    def validate_tool(cls, v):
        """Validate tool name against allowed tools."""
        allowed_tools = {
            "view_menu",
            "add_item",
            "remove_item",
            "read_back_cart",
            "finalize_order",
        }
        if v not in allowed_tools:
            raise ValueError(f"Invalid tool: {v}")
        return v


class ChatRequest(BaseModel):
    session_id: str = Field(default="demo-room", max_length=100)
    message: str = Field(max_length=2000)

    @validator("session_id")
    def validate_session_id(cls, v):
        """Validate session ID contains only safe characters."""
        if not v or not v.strip():
            raise ValueError("session_id cannot be empty")
        # Strict validation - reject path traversal attempts
        if ".." in v or "/" in v or "\\" in v:
            raise ValueError("session_id cannot contain path traversal characters")
        # Only allow alphanumeric, hyphens, and underscores
        if not all(c.isalnum() or c in "-_" for c in v):
            raise ValueError("session_id can only contain alphanumeric characters, hyphens, and underscores")
        return v[:100]

    @validator("message")
    def validate_message(cls, v):
        """Validate message is not empty."""
        if not v or not v.strip():
            raise ValueError("message cannot be empty")
        return v.strip()


class CheckoutRequest(BaseModel):
    payment_method: str | None = Field(default=None, max_length=50)
    customer_phone: str | None = Field(default=None, max_length=20)
    idempotency_key: str | None = Field(default=None, max_length=128)

    @validator("payment_method")
    def validate_payment_method(cls, v):
        """Validate payment method against allowed values."""
        if v is None:
            return v
        allowed_methods = {"cod", "upi", "card", "cash"}
        if v.lower() not in allowed_methods:
            raise ValueError(f"Invalid payment method: {v}")
        return v.lower()

    @validator("customer_phone")
    def validate_phone(cls, v):
        """Basic phone number validation (F18 fix)."""
        if v is None:
            return v
        # Remove common formatting characters
        cleaned = "".join(c for c in v if c.isdigit() or c == "+")
        if cleaned and (len(cleaned) < 10 or len(cleaned) > 15):
            raise ValueError("Phone number must be 10-15 digits")
        return cleaned if cleaned else None


class CleanupSessionsRequest(BaseModel):
    max_age_hours: float = Field(default=24.0, ge=0.5, le=720.0)


def _tools_for(session_id: str):
    r = get_repo()
    mgr = PersistentSessionManager(r)
    return create_order_tools(menu, session_id, session_manager=mgr, repository=r)


def _require_staff(authorization: str | None) -> dict[str, str]:
    """Require staff or admin authentication. Returns user info dict."""
    token = (authorization or "").replace("Bearer ", "").strip()
    user_info = verify_token(token)
    if not user_info or user_info.get("role") not in ("admin", "staff"):
        raise HTTPException(401, "Staff authentication required")
    return user_info


def _validate_session_id(session_id: str) -> str:
    """Validate and sanitize session_id path parameter."""
    if not session_id or not session_id.strip():
        raise HTTPException(400, "Session ID cannot be empty")
    if ".." in session_id or "/" in session_id or "\\" in session_id:
        raise HTTPException(400, "Session ID cannot contain path traversal characters")
    if not all(c.isalnum() or c in "-_" for c in session_id):
        raise HTTPException(400, "Session ID can only contain alphanumeric characters, hyphens, and underscores")
    if len(session_id) > 100:
        raise HTTPException(400, "Session ID too long (max 100 characters)")
    return session_id


def _groq_key_status() -> dict[str, str | bool]:
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        return {"configured": False, "valid_format": False, "hint": "Set GROQ_API_KEY in .env"}
    valid = key.startswith("gsk_") and len(key) > 20
    hint = "Key looks valid - if chat fails, regenerate at console.groq.com"
    if key.startswith('"') or key.startswith("'"):
        hint = "Remove quotes around the key in .env"
    elif not key.startswith("gsk_"):
        hint = "Groq keys start with gsk_ — check you copied the full key"
    elif len(key) < 20:
        hint = "Key looks truncated — copy the full key from console.groq.com"
    return {"configured": True, "valid_format": valid, "hint": hint}


@app.get("/api/menu")
def get_menu():
    m = load_menu()
    categories = {c["id"]: c["name"] for c in m.get("categories", [])}
    grouped: dict[str, list] = {}
    for item in m["items"]:
        cat = item.get("category", "other")
        grouped.setdefault(cat, []).append(
            {
                "id": item["id"],
                "name": item["name"],
                "description": item.get("description", ""),
                "category": cat,
                "category_name": categories.get(cat, cat.replace("-", " ").title()),
                "sizes": [
                    {
                        "id": sid,
                        "name": next((s["name"] for s in m["sizes"] if s["id"] == sid), sid),
                        "price_cents": pricing["base_price_cents"],
                    }
                    for sid, pricing in item["sizes"].items()
                ],
            }
        )
    return {
        "restaurant": m["restaurant"],
        "categories": m.get("categories", []),
        "items_by_category": grouped,
        "item_count": len(m["items"]),
    }


@app.get("/api/health")
def health():
    groq = _groq_key_status()
    use_edge = os.getenv("USE_EDGE_TTS", "false").lower() in ("1", "true", "yes")
    tts_label = "Edge TTS (fallback)" if use_edge else "Deepgram Aura (streaming)"
    db_ok = ping_database()
    status = "ok" if db_ok else "degraded"
    status_code = 200 if db_ok else 503
    payload = {
        "status": status,
        "restaurant": menu["restaurant"]["name"],
        "items": len(menu["items"]),
        "modifiers": len(menu["modifiers"]),
        "database": "connected" if db_ok else "unreachable",
        "free_stack": {
            "llm": "Groq gpt-oss-20b (voice)",
            "tts": tts_label,
            "stt": "Deepgram nova-3",
            "vad": "Silero (local)",
            "db": "SQLite local (default)",
            "livekit": "LiveKit Cloud free tier",
        },
        "chat_mode": "groq" if groq["configured"] else "keyword_fallback",
        "groq": groq,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return JSONResponse(status_code=status_code, content=payload)


@app.get("/api/sessions")
def list_sessions(authorization: str | None = Header(default=None)):
    _require_staff(authorization)
    return {"sessions": get_repo().list_active_sessions()}


@app.post("/api/sessions/cleanup")
def cleanup_abandoned_sessions(
    req: CleanupSessionsRequest = CleanupSessionsRequest(),
    authorization: str | None = Header(default=None),
):
    """Staff endpoint to purge stale, abandoned shopping sessions."""
    _require_staff(authorization)
    cleaned = get_repo().cleanup_abandoned_sessions(max_age_hours=req.max_age_hours)
    return {"cleaned_sessions": cleaned, "max_age_hours": req.max_age_hours}


@app.post("/api/sessions/{session_id}/start")
def start_order_session(session_id: str):
    """Start or restart an ordering session (clears cart if a previous order was finalized)."""
    clean_id = _validate_session_id(session_id)
    return get_repo().restart_session(clean_id)


@app.get("/api/sessions/{session_id}/cart")
def get_session_cart(session_id: str):
    """Get cart for a session without restarting it (F15 fix - removed restart side effect)."""
    clean_id = _validate_session_id(session_id)
    try:
        cart = get_repo().load_cart(clean_id)
        return cart_summary_to_dict(cart.summarize(menu))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/sessions/{session_id}/checkout")
def get_session_checkout(session_id: str):
    clean_id = _validate_session_id(session_id)
    try:
        return get_repo().get_checkout_details(clean_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/sessions/{session_id}/checkout")
def set_session_checkout(session_id: str, req: CheckoutRequest):
    clean_id = _validate_session_id(session_id)
    try:
        return get_repo().set_checkout_details(
            clean_id,
            payment_method=req.payment_method,
            customer_phone=req.customer_phone,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/orders")
def list_orders(limit: int = 50, authorization: str | None = Header(default=None)):
    _require_staff(authorization)
    return {"orders": get_repo().list_orders(limit=limit)}


@app.get("/api/calls")
def list_calls(limit: int = 50, authorization: str | None = Header(default=None)):
    _require_staff(authorization)
    return {"calls": get_repo().list_call_logs(limit=limit)}


@app.post("/api/tools/invoke")
def invoke_tool(req: ToolRequest):
    get_repo().restart_session(req.session_id)
    tools = _tools_for(req.session_id)
    result = execute_tool(tools, req.tool, req.args)
    return tool_result_to_dict(result)


@app.post("/api/chat")
def text_chat(req: ChatRequest):
    """Text chat — Groq + same order tools as voice; keyword fallback without GROQ_API_KEY."""
    get_repo().restart_session(req.session_id)
    tools = _tools_for(req.session_id)
    agent = GroqChatAgent(tools, get_repo(), req.session_id)
    return agent.chat(req.message)


LIVEKIT_AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME", "dialog-order-agent")


def _livekit_credentials() -> tuple[str, str, str]:
    url = os.getenv("LIVEKIT_URL")
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")
    if not all([url, api_key, api_secret]):
        raise HTTPException(
            503,
            "LiveKit not configured. Free signup at https://cloud.livekit.io",
        )
    return url, api_key, api_secret


@app.get("/api/livekit/token")
def livekit_token(room: str = "demo-room", identity: str = "web-customer"):
    clean_room = _validate_session_id(room)
    url, api_key, api_secret = _livekit_credentials()
    from livekit.api import AccessToken, VideoGrants

    token = (
        AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_name(identity)
        .with_grants(VideoGrants(room_join=True, room=clean_room))
        .to_jwt()
    )
    return {"url": url, "token": token, "room": clean_room}


@app.post("/api/livekit/dispatch")
async def dispatch_voice_agent(room: str):
    """Start the voice agent in a room after the customer connects their microphone."""
    clean_room = _validate_session_id(room)
    get_repo().restart_session(clean_room)
    url, api_key, api_secret = _livekit_credentials()
    from livekit import api
    from livekit.protocol.agent_dispatch import CreateAgentDispatchRequest

    lkapi = api.LiveKitAPI(url, api_key, api_secret)
    try:
        dispatch = await lkapi.agent_dispatch.create_dispatch(
            CreateAgentDispatchRequest(agent_name=LIVEKIT_AGENT_NAME, room=clean_room)
        )
        return {"dispatch_id": dispatch.id, "agent_name": LIVEKIT_AGENT_NAME, "room": clean_room}
    finally:
        await lkapi.aclose()


@app.delete("/api/livekit/voice-session")
async def end_voice_session(room: str):
    """Remove agent dispatches when the customer session goes offline."""
    clean_room = _validate_session_id(room)
    url, api_key, api_secret = _livekit_credentials()
    from livekit import api

    lkapi = api.LiveKitAPI(url, api_key, api_secret)
    removed = 0
    try:
        dispatches = await lkapi.agent_dispatch.list_dispatch(clean_room)
        for dispatch in dispatches:
            await lkapi.agent_dispatch.delete_dispatch(dispatch.id, clean_room)
            removed += 1
        return {"room": clean_room, "dispatches_removed": removed}
    finally:
        await lkapi.aclose()


@app.websocket("/ws/sessions/{session_id}")
async def cart_websocket(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for live cart updates with validation."""
    # Validate and sanitize session_id to prevent path traversal
    safe_session_id = "".join(c for c in session_id if c.isalnum() or c in "-_")
    if not safe_session_id or len(safe_session_id) > 100:
        await websocket.close(code=1008, reason="Invalid session ID")
        return

    await websocket.accept()
    get_repo().restart_session(safe_session_id)
    last_payload = None
    update_count = 0
    max_updates = 3600  # Limit updates per connection (1 hour at 1 second intervals)

    try:
        while update_count < max_updates:
            cart = get_repo().load_cart(safe_session_id)
            payload = cart_summary_to_dict(cart.summarize(menu))
            if payload != last_payload:
                await websocket.send_json({"type": "cart_update", "cart": payload})
                last_payload = payload
            await asyncio.sleep(1)
            update_count += 1
    except WebSocketDisconnect:
        pass
    except ValueError as exc:
        await websocket.send_json({"type": "error", "message": "Session error"})
    except Exception:
        # Don't leak internal errors to WebSocket client
        await websocket.send_json({"type": "error", "message": "Internal error"})


@app.get("/")
def landing():
    return FileResponse(STATIC_DIR / "landing.html")


@app.get("/dashboard")
def dashboard():
    return FileResponse(STATIC_DIR / "index.html")


def run() -> None:
    import uvicorn

    # Bind to localhost by default for security (F21 fix)
    # For production deployment, set HOST=0.0.0.0 in environment
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "3000"))
    uvicorn.run("web.main:app", host=host, port=port, reload=True)
