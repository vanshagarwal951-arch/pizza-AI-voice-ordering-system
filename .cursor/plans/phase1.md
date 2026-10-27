# Phase 1: Real-Time Voice Restaurant Ordering System

> **Goal:** Ship a working monorepo where a voice agent takes pizza orders via strict tool calls, validated by a code-level "Judge" (menu engine) — never by the LLM.

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        apps/voice-server                        │
│  LiveKit Agents / Pipecat pipeline                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────────┐ │
│  │ Deepgram │→ │   LLM    │→ │ Tool     │→ │ Cartesia /      │ │
│  │   STT    │  │ (tools   │  │ Executor │  │ ElevenLabs TTS  │ │
│  │          │  │  only)   │  │          │  │                 │ │
│  └──────────┘  └──────────┘  └────┬─────┘  └─────────────────┘ │
└───────────────────────────────────│─────────────────────────────┘
                                    │ add_item / remove_item / read_back_cart
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                     packages/menu-engine                        │
│  "The Judge" — deterministic validation, pricing, cart state    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Prisma + PG  │  │ OrderBuilder │  │ Validation Rules     │  │
│  │ (menu schema)│  │ (cart state) │  │ (86'd, half-half,    │  │
│  │              │  │              │  │  modifier limits)    │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                          apps/web                               │
│  Next.js dashboard scaffold — live cart view, order history     │
└─────────────────────────────────────────────────────────────────┘
```

### Core Domain Rule (Non-Negotiable)

The LLM **must never** write, compute, or mutate order state directly. It can **only** invoke three tools:

| Tool | Purpose |
|------|---------|
| `add_item` | Add a validated line item to the cart |
| `remove_item` | Remove a line item by cart ID |
| `read_back_cart` | Return human-readable cart summary for confirmation |

All validation, pricing, and cart mutation happens inside `menu-engine`. Tool responses include structured success/error payloads the LLM reads aloud.

---

## 2. Monorepo Structure

```
/
├── apps/
│   ├── voice-server/          # LiveKit Agents / Pipecat voice pipeline
│   │   ├── src/
│   │   │   ├── agent.ts         # Main agent entry (LiveKit Worker)
│   │   │   ├── pipeline/        # STT → LLM → TTS pipeline config
│   │   │   ├── tools/           # Thin wrappers → menu-engine
│   │   │   └── prompts/         # System prompt (tool-only ordering)
│   │   ├── package.json
│   │   └── tsconfig.json
│   │
│   └── web/                     # Next.js 15 dashboard scaffold
│       ├── app/
│       │   ├── layout.tsx
│       │   ├── page.tsx         # Dashboard home
│       │   └── api/             # REST endpoints (cart sync later)
│       ├── package.json
│       └── next.config.ts
│
├── packages/
│   └── menu-engine/             # "The Judge"
│       ├── prisma/
│       │   ├── schema.prisma    # Menu DB schema
│       │   └── seed.ts          # Seed pizza menu data
│       ├── src/
│       │   ├── index.ts         # Public API exports
│       │   ├── menu/            # Menu loader & queries
│       │   ├── cart/            # Cart state machine
│       │   ├── validation/      # Rule engine
│       │   │   ├── rules/       # Individual rule modules
│       │   │   └── validator.ts
│       │   └── tools/           # add_item, remove_item, read_back_cart
│       ├── tests/               # Vitest TDD suite
│       ├── package.json
│       └── tsconfig.json
│
├── data/
│   └── menu/
│       └── pizza-menu.json      # Source-of-truth menu (seed input)
│
├── package.json                 # Root workspace (pnpm)
├── pnpm-workspace.yaml
├── turbo.json                   # Turborepo task orchestration
├── tsconfig.base.json
└── .env.example
```

---

## 3. Menu Schema Design

### 3a. JSON Source (`data/menu/pizza-menu.json`)

Human-readable seed file defining:

- **Categories:** Pizzas, Sides, Drinks
- **Items:** Each pizza with available sizes (S/M/L/XL), base price per size
- **Modifiers:** Toppings (regular/extra), crust types, sauce swaps
- **Modifier groups:** `toppings_left`, `toppings_right`, `whole_toppings`, `crust`, `sauce`
- **Availability flags:** `is_86d` (out of stock), `is_available`
- **Half-and-half rules:** Left/right topping groups, max toppings per side, extra-cheese per-side flag

Example structure:

```json
{
  "restaurant": { "name": "Tony's Pizza", "currency": "USD" },
  "sizes": [
    { "id": "small", "name": "Small", "inches": 10 },
    { "id": "large", "name": "Large", "inches": 14 }
  ],
  "items": [
    {
      "id": "build-your-own",
      "name": "Build Your Own Pizza",
      "category": "pizza",
      "sizes": {
        "small": { "base_price_cents": 999 },
        "large": { "base_price_cents": 1499 }
      },
      "modifier_groups": ["whole_toppings", "toppings_left", "toppings_right", "crust"]
    }
  ],
  "modifiers": [
    { "id": "pepperoni", "name": "Pepperoni", "group": "toppings", "price_cents": 150, "is_86d": false },
    { "id": "mushroom", "name": "Mushroom", "group": "toppings", "price_cents": 125, "is_86d": false },
    { "id": "extra_cheese", "name": "Extra Cheese", "group": "toppings", "price_cents": 175, "is_86d": false }
  ],
  "rules": {
    "half_and_half": {
      "requires_both_sides": true,
      "max_toppings_per_side": 5,
      "extra_cheese_side_specific": true
    },
    "max_whole_toppings": 8
  }
}
```

### 3b. Prisma / Postgres Schema

```prisma
model MenuItem {
  id          String   @id
  name        String
  category    String
  isAvailable Boolean  @default(true)
  sizes       MenuItemSize[]
  modifierGroups MenuItemModifierGroup[]
}

model MenuItemSize {
  id            String @id @default(cuid())
  menuItemId    String
  sizeId        String
  basePriceCents Int
  menuItem      MenuItem @relation(...)
}

model Modifier {
  id          String  @id
  name        String
  group       String
  priceCents  Int
  is86d       Boolean @default(false)
}

model OrderSession {
  id        String   @id @default(cuid())
  cartItems CartItem[]
  createdAt DateTime @default(now())
}

model CartItem {
  id            String @id @default(cuid())
  sessionId     String
  menuItemId    String
  sizeId        String
  isHalfAndHalf Boolean @default(false)
  leftToppings  Json?   // [{ modifierId, extra: bool }]
  rightToppings Json?
  wholeToppings Json?
  crustId       String?
  lineTotalCents Int
}
```

Phase 1 uses an **in-memory cart** backed by the JSON menu file. Prisma schema is scaffolded for Phase 2 persistence but seed runs from JSON.

---

## 4. Menu Engine — Validation Rules ("The Judge")

| Rule ID | Description | Example Failure |
|---------|-------------|-----------------|
| `R01` | Item must exist and be available | "We don't carry calzones" |
| `R02` | Size must be valid for item | "Large not available on personal pizza" |
| `R03` | Modifier must exist, not 86'd | "Mushrooms are 86'd tonight" |
| `R04` | Modifier must belong to allowed group for item | "Can't add pepperoni to a drink" |
| `R05` | Half-and-half requires both sides populated | Missing right-side toppings |
| `R06` | Max toppings per side (half-and-half) | "Max 5 toppings per side" |
| `R07` | Side-specific extra cheese | Extra cheese on pepperoni side only |
| `R08` | Duplicate topping dedup | Same topping twice on one side |
| `R09` | Pricing computed server-side | LLM never sees raw prices until read_back |
| `R10` | Remove requires valid cart line ID | "I can't find that item in your cart" |

### Tool Signatures

```typescript
// packages/menu-engine/src/tools/types.ts

interface AddItemInput {
  menu_item_id: string;
  size_id: string;
  is_half_and_half?: boolean;
  left_toppings?: Array<{ modifier_id: string; extra?: boolean }>;
  right_toppings?: Array<{ modifier_id: string; extra?: boolean }>;
  whole_toppings?: Array<{ modifier_id: string; extra?: boolean }>;
  crust_id?: string;
  quantity?: number; // default 1
}

interface ToolResult {
  success: boolean;
  message: string;          // Human-readable for TTS
  cart_item_id?: string;    // On success
  error_code?: string;      // On failure (R01–R10)
  cart_summary?: CartSummary; // Included on read_back_cart
}
```

---

## 5. TDD Test Plan (`packages/menu-engine/tests/`)

Tests written **first**, using Vitest. Menu loaded from fixture JSON.

### Test Suite: `validation.test.ts`

| # | Test Case | Expected |
|---|-----------|----------|
| T1 | Add simple large pepperoni pizza | Success, correct line total |
| T2 | Add 86'd topping (anchovies) | Fail R03 with spoken message |
| T3 | Invalid size for item | Fail R02 |
| T4 | **Large half-pepperoni half-mushroom** | Success, two sides populated |
| T5 | **Extra cheese on pepperoni side only** | Success, extra flag on left only |
| T6 | Half-and-half with only left side | Fail R05 |
| T7 | Exceed max toppings per side (6 on left) | Fail R06 |
| T8 | Duplicate topping on same side | Fail R08 (dedup) |
| T9 | Remove item by cart ID | Success, cart empty |
| T10 | Remove non-existent cart ID | Fail R10 |
| T11 | `read_back_cart` with 2 items | Correct summary + total |
| T12 | Whole pizza with 9 toppings | Fail max whole toppings rule |

### Test Suite: `pricing.test.ts`

| # | Test Case | Expected |
|---|-----------|----------|
| P1 | Base + 2 regular toppings | Correct cents total |
| P2 | Extra cheese modifier pricing | +175 cents per side |
| P3 | Half-and-half with different topping counts | Priced per side |

### Test Suite: `tools.test.ts`

| # | Test Case | Expected |
|---|-----------|----------|
| TO1 | `add_item` returns ToolResult shape | Typed response |
| TO2 | Sequential adds accumulate cart | 2 items in cart |
| TO3 | LLM cannot bypass validator (no direct cart mutation export) | Only tool functions exported |

---

## 6. Voice Pipeline (`apps/voice-server`)

### Stack Choice

**Primary:** LiveKit Agents SDK (TypeScript) — production-grade, built-in interruption/VAD.

**Fallback reference:** Pipecat pipeline config kept in `pipeline/pipecat.ts` for portability.

### Pipeline Flow

```
Mic (LiveKit room)
  → Deepgram STT (nova-2, interim results, utterance_end)
  → LLM (GPT-4o / Claude) with tool definitions ONLY
  → Tool executor → menu-engine
  → Cartesia TTS (primary) / ElevenLabs (fallback)
  → Speaker (LiveKit room)
```

### Interruption Handling

1. **VAD + barge-in:** LiveKit Agents `VoicePipelineAgent` with `allow_interruptions: true`
2. **STT endpointing:** Deepgram `utterance_end_ms: 1000` + `interim_results: true`
3. **TTS cancel:** On user speech detected during TTS playback, cancel current audio frame and flush buffer
4. **Tool-in-flight guard:** If a tool call is executing when user interrupts, cancel TTS but let tool complete; LLM re-evaluates with updated context
5. **Confirmation loop:** After `add_item` success, agent reads back item; after checkout intent, calls `read_back_cart`

### System Prompt (Key Constraints)

```
You are a friendly pizza order taker. You MUST use tools for ALL order changes.
NEVER invent prices, items, or cart contents. NEVER say an item was added unless
add_item returns success. If a tool returns an error, apologize and ask the customer
to adjust. Always confirm the full cart before finalizing.
```

### Environment Variables (`.env.example`)

```
LIVEKIT_URL=
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=
DEEPGRAM_API_KEY=
OPENAI_API_KEY=          # or ANTHROPIC_API_KEY
CARTESIA_API_KEY=
ELEVENLABS_API_KEY=      # fallback TTS
DATABASE_URL=            # postgres (Phase 2)
```

---

## 7. Web Dashboard Scaffold (`apps/web`)

Phase 1 scope is **scaffold only**:

- Next.js 15 App Router, Tailwind CSS
- `/` — placeholder dashboard with "Voice Ordering System" header
- `/api/health` — health check endpoint
- Shared types imported from `@repo/menu-engine`
- No real-time cart sync yet (Phase 2: LiveKit data channel or WebSocket)

---

## 8. Implementation Order

| Step | Task | Deliverable | Est. |
|------|------|-------------|------|
| **1** | Monorepo bootstrap | `pnpm-workspace.yaml`, root `package.json`, `turbo.json`, shared TS config | 30 min |
| **2** | Menu JSON + Prisma schema | `data/menu/pizza-menu.json`, `schema.prisma`, seed script | 45 min |
| **3** | Menu engine — TDD tests | All 15+ test cases in Vitest (red) | 1 hr |
| **4** | Menu engine — implementation | Validator, cart, tools (green) | 2 hr |
| **5** | Voice server — tool wiring | Thin tool wrappers, system prompt | 1 hr |
| **6** | Voice server — pipeline | LiveKit agent + Deepgram + TTS + interruption | 2 hr |
| **7** | Web scaffold | Next.js dashboard shell | 30 min |
| **8** | Integration smoke test | Manual voice order end-to-end | 1 hr |

**Total estimate: ~8–9 hours**

---

## 9. Phase 1 Exit Criteria

- [x] Monorepo structure scaffolded (`pnpm install && pnpm build` — requires Node 20+ locally)
- [x] All menu-engine tests written (18 cases across validation, pricing, tools)
- [x] Complex order test implemented: *"Large half-pepperoni half-mushroom, extra cheese on pepperoni side"* (T4 + T5)
- [x] Voice agent scaffold with LiveKit + tool wiring + interruption config
- [x] Agent system prompt enforces tool-only ordering
- [x] Interruption policy configured (`allowInterruptions`, utterance endpointing)
- [x] 86'd item rejection test (T2) + spoken error message
- [x] Web dashboard scaffold at `apps/web` (run `pnpm dev` → localhost:3000)
- [ ] End-to-end voice smoke test (requires LiveKit + API keys in `.env`)

---

## 10. Phase 2 Preview (Out of Scope)

- Postgres persistence for orders & sessions
- Web dashboard live cart sync
- Payment integration
- Multi-restaurant menu support
- Order kitchen display system (KDS)
- Analytics & call recording

---

## 11. Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Monorepo tool | pnpm workspaces + Turborepo | Fast builds, shared types |
| Test runner | Vitest | Native TS, fast, ESM-friendly |
| Voice framework | LiveKit Agents SDK | Built-in VAD, interruption, production-ready |
| STT | Deepgram nova-2 | Best latency for real-time, utterance endpointing |
| TTS primary | Cartesia | Sub-100ms latency, streaming |
| TTS fallback | ElevenLabs | Quality fallback if Cartesia unavailable |
| Menu source of truth | JSON → Prisma seed | Easy to edit, version-control friendly |
| Cart state (Phase 1) | In-memory per session | Simplicity; DB in Phase 2 |
| LLM | GPT-4o or Claude 3.5 Sonnet | Strong tool-calling reliability |

---

## 12. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| LLM hallucinates order items | Strict tool-only prompt + no cart state in LLM context except via `read_back_cart` |
| Half-and-half parsing ambiguity | Structured tool params (left/right arrays), not free text |
| TTS latency breaks conversation flow | Cartesia streaming + short confirmation phrases |
| Deepgram misrecognizes topping names | Fuzzy match modifier IDs in validator with suggestion message |
| Interruption during tool call | Tool completes atomically; LLM re-syncs via read_back |

---

*Ready for review. Upon approval, implementation begins at Step 1.*
