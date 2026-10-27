# Voice Ordering System — Complete Project

Real-time AI pizza ordering with **The Judge** (code-level menu validation), voice agent, kitchen tickets, and operator dashboard.

## Free Stack (Default)

| Layer | Tool | Cost |
|-------|------|------|
| Database | SQLite (local file) | Free |
| LLM | [Groq](https://console.groq.com) | Free tier |
| STT | [Deepgram](https://console.deepgram.com) | $200 free credit |
| TTS | Edge TTS (Microsoft) | Free |
| Voice rooms | [LiveKit Cloud](https://cloud.livekit.io) | Free tier |
| VAD | Silero (local) | Free |

**Text chat:** keyword demo works without keys; set `GROQ_API_KEY` for full AI chat (same tools as voice).

---

## Quick Start (5 minutes)

```powershell
cd C:\Users\vansh\Projects
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env

# Dashboard
python -m uvicorn web.main:app --app-dir apps/web --reload --port 3000
```

Open **http://localhost:3000** → **Text Chat Demo** (keyword mode without keys, Groq AI with `GROQ_API_KEY`).

---

## Full Voice Setup

1. **Groq** — free API key → `GROQ_API_KEY` (also powers text chat)
2. **Deepgram** — free API key → `DEEPGRAM_API_KEY`
3. **LiveKit Cloud** — free project → `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`
4. **ffmpeg** — required for Edge TTS: `winget install Gyan.FFmpeg`

```powershell
# Check all voice prerequisites
.\scripts\check_prerequisites.ps1

# Terminal 1 — Dashboard
python -m uvicorn web.main:app --app-dir apps/web --reload --port 3000

# Terminal 2 — Voice agent (checks keys + ffmpeg first)
.\scripts\start_voice.ps1
# Uses `agent.py start` (production worker). For hot-reload, install LiveKit CLI: lk agent dev
```

On dashboard: set session to `demo-room` → **Connect Voice (Browser)** → talk to the agent.

---

## Optional: Postgres

```powershell
docker compose up -d
# Uncomment DATABASE_URL in .env
python scripts/init_db.py
```

---

## Project Structure

```
apps/voice_server/     LiveKit voice agent (Groq + Deepgram + Edge TTS)
apps/web/              Operator dashboard + text chat + WebSocket live cart
packages/menu_engine/    The Judge — validation, cart, Postgres/SQLite, kitchen
data/menu/               Menu JSON source of truth
data/tickets/            Kitchen tickets (JSON files on finalize)
data/notifications/      Order notification logs
scripts/                 init_db.py, generate_token.py, check_prerequisites.ps1, start_voice.ps1
```

---

## Tools (LLM can ONLY call these)

| Tool | Purpose |
|------|---------|
| `add_item` | Add validated item to cart |
| `remove_item` | Remove by cart line ID |
| `read_back_cart` | Spoken confirmation |
| `finalize_order` | Submit to kitchen + mock POS + notify |
| `transfer_to_human` | Escalate to staff |

---

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Operator dashboard |
| `GET /api/health` | System status |
| `GET /api/sessions/{id}/cart` | Cart snapshot |
| `GET /api/orders` | Order history |
| `GET /api/calls` | Call logs + transcripts |
| `POST /api/chat` | Groq text chat (keyword fallback without key) |
| `POST /api/tools/invoke` | Direct tool testing |
| `GET /api/livekit/token` | Browser voice token |
| `WS /ws/sessions/{id}` | Live cart stream |

---

## Tests

```powershell
pytest packages/menu_engine/tests -q
# 21+ tests including half-and-half, 86'd items, persistence
```

---

## Architecture

```
Customer (browser/phone)
    → LiveKit room
    → Voice Agent (STT → Groq LLM → tools → Edge TTS)
    → Menu Engine ("The Judge")
    → SQLite/Postgres + Kitchen ticket + Mock POS
    → Dashboard (live cart WebSocket)
```

**Core rule:** The LLM never writes orders — only calls tools. Validation is in code.
