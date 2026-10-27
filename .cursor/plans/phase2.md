# Phase 2: Persistence & Live Dashboard

> **Goal:** Persist carts/orders in Postgres, sync live cart to the web dashboard, and support order finalization.

---

## Scope

| Feature | Deliverable |
|---------|-------------|
| Postgres persistence | SQLAlchemy models: `OrderSession`, `CartItem`, `Order` |
| Shared cart state | Voice agent + web read/write same DB |
| Live cart sync | WebSocket `/ws/sessions/{id}` on dashboard |
| Order finalization | `finalize_order` tool + order history API |
| Infrastructure | `docker-compose.yml` for Postgres |

**Out of scope (Phase 3):** Payments, multi-restaurant, KDS, analytics

---

## Architecture

```
Voice Agent (tool call)
       │
       ▼
OrderTools → CartRepository → PostgreSQL
       ▲                           │
       │                           │
Web Dashboard ← REST + WebSocket ──┘
```

---

## Exit Criteria

- [x] `docker compose up -d` starts Postgres
- [x] Cart survives voice server restart (loaded from DB via `CartRepository`)
- [x] Dashboard shows live cart via WebSocket `/ws/sessions/{room_name}`
- [x] `finalize_order` creates order record, locks session
- [x] `/api/orders` returns order history
- [x] Persistence tests pass (21 total tests, SQLite in-memory)
