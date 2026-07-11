# MK AI Assistant — Architecture

This document describes how MK's all-in-one, context-aware AI assistant is put
together: how the web API, the **MK wrapper**, the engine, the LLM router, and
memory fit together; the lifecycle of a chat request; how context-awareness
flows from the current screen to the answer; and where the OS/terminal path
plugs in.

> **Scope.** This is the architecture for the *assistant* surface. It focuses on
> the chat/suggestions path introduced by the wrapper. Domain features
> (storage, apps, network, …) are separate API routers that the assistant can
> reference but do not depend on it.

---

## 1. High-level picture

```
┌──────────────────────────────────────────────────────────────────────┐
│                             Clients                                    │
│                                                                        │
│   Web UI (React/Vite)              OS / Terminal (mk-shell, chat.py)   │
│   • ChatPanel + ChatInput          • REPL / one-shot prompt            │
│   • ContextSuggestions             • same typed contract               │
│   • ChatBubble (failure-aware)                                         │
└───────────────┬───────────────────────────────┬───────────────────────┘
                │ HTTP POST /api/v1/chat/message │ (future) in-process call
                │ WS   /ws/chat                  │
                │ GET  /api/v1/chat/suggestions  │
                ▼                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    Web API  (src/mk/web/app.py, FastAPI)               │
│   • Auth, request-id, HTTP↔envelope mapping                            │
│   • Validates into ChatRequest, maps InputValidationError → HTTP 422   │
└───────────────────────────────┬───────────────────────────────────────┘
                                 │  ChatRequest  (typed contract)
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    MK Wrapper  (src/mk/wrapper/)                        │
│   The single, robust integration point to the engine.                  │
│   • Strict input validation      • Timeout / deadline enforcement      │
│   • AI-failure detection          • Safe fallbacks (never crashes)     │
│   • Context-aware suggestions     • Metrics + structured logging       │
│   Returns a uniform ChatResult to every caller.                        │
└───────────────────────────────┬───────────────────────────────────────┘
                                 │  engine.process(str) -> AgentResponse
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    MK Engine  (src/mk/core/)                           │
│   engine.py / engine_v2.py                                             │
│   • agent_loop.py     — plan/act/observe loop                          │
│   • command_router.py — deterministic command shortcuts (no-LLM path)  │
│   • context.py        — engine-side working context                    │
└───────────────┬──────────────────────────────┬────────────────────────┘
                │                               │
                ▼                               ▼
┌───────────────────────────┐      ┌───────────────────────────────────┐
│  LLM Router (src/mk/llm/)  │      │  Memory (src/mk/memory/)          │
│  • router.py — provider    │      │  • short_term.py / long_term.py   │
│    selection + fallback    │      │  • sqlite_store.py, vector/       │
│  • provider_factory.py     │      │  • system_state.py (live facts)   │
│  • providers/* (OpenAI,    │      │                                   │
│    Anthropic, local, …)    │      │                                   │
│  • token_manager, keys     │      │                                   │
└───────────────────────────┘      └───────────────────────────────────┘
```

**Key idea:** every caller — the web API today, the OS/terminal path
tomorrow — goes through the **same wrapper** and receives the **same
`ChatResult` shape**. Validation, timeouts, AI-failure handling, and
context-awareness are implemented once and shared.

---

## 2. Components

### 2.1 Web UI (`webui/`)
- **`components/layout/ChatPanel.tsx`** — the persistent right-hand chat panel.
  Sends messages to `POST /api/v1/chat/message`, always including the current
  route as page context, and renders replies (including AI-failure fallbacks).
- **`components/chat/ContextSuggestions.tsx`** — page-aware suggestion chips.
  Fetches `GET /api/v1/chat/suggestions?path=…` via the `useSuggestions` SWR
  hook (`hooks/useApi.ts`). Handles loading / empty / error states gracefully.
- **`components/chat/ChatBubble.tsx`** — renders a message. When a reply is an
  AI-failure fallback (`ok === false`) it is shown as an accessible alert
  (`role="alert"`) with a friendly, non-technical label; degraded (no-LLM)
  replies get a "Limited mode" badge.
- **`stores/chatStore.ts`** — Zustand store holding the conversation, streaming
  state, and per-message failure metadata (`ok`, `failureType`, `degraded`).
- **`hooks/useChat.ts` + `lib/ws.ts`** — the WebSocket path (`/ws/chat`) with
  reconnection/heartbeat; it threads the same failure metadata through.
- **`types/chat.ts`** — TypeScript mirror of the backend contract (kept in sync
  with `src/mk/wrapper/models.py`).

### 2.2 Web API (`src/mk/web/app.py`)
- Owns authentication, the per-request `request_id`, and the HTTP/WS envelope.
- Builds a `ChatRequest` from the incoming payload and calls the wrapper.
- Translates `InputValidationError` into **HTTP 422**; every other problem is
  already handled inside the wrapper and returned as a normal `200` envelope
  with `ok: false`.
- Endpoints:
  - `POST /api/v1/chat/message` → `ChatResponse`
  - `GET  /api/v1/chat/suggestions?path=&limit=` → `SuggestionsResponse`
  - `GET  /api/v1/chat/history`
  - `WS   /ws/chat` (typed `chat_message` / `chat_response` frames)

### 2.3 MK Wrapper (`src/mk/wrapper/`)
The heart of this design. See `wrapper.py` for the implementation.

| Module | Responsibility |
| --- | --- |
| `models.py` | Typed contract: `ChatRequest`, `PageContext`, `SuggestedAction`, `ChatResult`, `AIFailureInfo`. Strict input validation. |
| `errors.py` | `AIFailureType` taxonomy + `InputValidationError` (client errors). |
| `failures.py` | Pure detectors for empty / degenerate / schema-invalid output. |
| `context.py` | Route-prefix → label + suggestions mapping (longest-prefix wins). |
| `wrapper.py` | `MKWrapper.chat()` orchestration, timeouts, lazy engine build, metrics. |

The wrapper only requires the engine to expose an async
`process(str) -> AgentResponse`, so it works with `MKEngine`, `MKEngineV2`, and
test doubles.

### 2.4 Engine (`src/mk/core/`)
- **`agent_loop.py`** runs the plan/act/observe loop when an LLM is available.
- **`command_router.py`** provides deterministic command shortcuts that work
  **without** an LLM — this is what powers "degraded" (command-only) mode.
- **`engine.py` / `engine_v2.py`** wire these together with tools and memory.

### 2.5 LLM Router (`src/mk/llm/`)
- **`router.py`** picks a provider and falls back across providers on failure.
- **`provider_factory.py` / `providers/*`** implement individual backends.
- **`token_manager.py` / `keys.py`** handle budgeting and credential storage.
- Provider-layer exceptions (`mk.llm.base.ProviderError`) are classified by the
  wrapper as `provider_unavailable`.

### 2.6 Memory (`src/mk/memory/`)
- **`short_term.py`** — recent conversation window.
- **`long_term.py` / `sqlite_store.py` / `vector/`** — durable recall.
- **`system_state.py`** — live system facts the assistant can ground answers in.

---

## 3. Chat request lifecycle

`POST /api/v1/chat/message` (the WS path is equivalent):

1. **Auth + request-id.** The API authenticates and attaches a `request_id`.
2. **Validate.** The payload becomes a `ChatRequest`. Bad input (empty /
   oversized content) raises `InputValidationError` → **HTTP 422**. `context`
   is normalized by `PageContext.from_raw` (accepts a path string, dict, or
   `{path|pathname|route}` keys; garbage degrades to the dashboard context).
3. **Suggestions.** The wrapper computes context-aware `SuggestedAction`s for
   the page (returned alongside the answer as follow-ups).
4. **Engine acquisition.** `MKWrapper._get_engine()` returns the engine,
   lazily building a safe default **at most once** if none was injected. If it
   still can't be built → `no_engine` failure with a safe message.
5. **Bounded execution.** `engine.process(content)` runs under
   `asyncio.wait_for(timeout=60s)`.
   - Timeout → `timeout` failure (retryable).
   - Exception → `provider_unavailable` (for `ProviderError`) or `engine_error`.
6. **Output inspection.** The raw text is checked by `detect_output_failure`
   for `empty_output`, `malformed_output` (runaway repetition), and — when
   `expects_json` — `schema_invalid`.
7. **Uniform result.** A `ChatResult` is returned: `ok`, `content` (answer or
   safe fallback), `actions`, `failure`, `degraded`, `llm_available`,
   `tokens_used`, `cost`, `provider_used`, `request_id`.
8. **Envelope.** The API maps `ChatResult` → `ChatResponse` and returns `200`.
   The UI renders normally, or shows a failure/degraded bubble.

```
content ──▶ validate ──▶ suggestions ──▶ get_engine ──▶ process (≤60s)
                                              │                │
                                        no_engine          timeout / error
                                              │                │
                                              ▼                ▼
                                        ┌──────────────────────────┐
                                        │  detect_output_failure    │
                                        │  (empty/malformed/schema) │
                                        └───────────┬───────────────┘
                                                    ▼
                                            ChatResult (ok / !ok)
```

---

## 4. Context-awareness flow

Context-awareness means the assistant knows *where the user is* and offers the
right shortcuts and grounds its answers accordingly.

1. **The UI knows the route.** `ContextSuggestions` reads `useLocation()` and
   calls `useSuggestions(pathname)` → `GET /api/v1/chat/suggestions?path=…`.
2. **The backend owns the mapping.** `wrapper/context.py` maps a route prefix
   to a human label and an ordered list of suggestions, **longest-prefix wins**
   (so `/media-manager` is not shadowed by `/media`). This is the single source
   of truth — the UI no longer hard-codes suggestions.
3. **Chips render.** Each chip shows a short `label`; clicking sends the
   suggestion's `prompt` into the chat. Loading/empty/error states are handled
   so the panel never breaks.
4. **Messages carry context.** Every user message includes
   `context: { path }`. The wrapper attaches the page's suggestions to the
   response and can enrich the engine prompt with the current screen.

```
route change ─▶ useSuggestions(path) ─▶ GET /chat/suggestions
                                            │
                                            ▼
                                   wrapper/context.suggestions_for()
                                            │ longest-prefix match
                                            ▼
                              SuggestionsResponse { context_label, suggestions[] }
                                            │
                                            ▼
                                   ContextSuggestions chips ─▶ prompt ─▶ chat
```

Because both suggestions and chat go through the same `PageContext`, the chips
always reflect what the assistant can actually do on the current screen.

---

## 5. Integration point for the OS / terminal path

The wrapper was designed so the OS/terminal experience reuses it **without a
web server**:

- **Same contract.** A terminal front-end (`src/mk/chat.py`, `mk-shell`)
  constructs a `ChatRequest` — `content`, an optional `PageContext` describing
  the "screen" (e.g. `/system` while viewing services, or a synthetic path for
  a TUI view), and `expects_json` for structured commands.
- **Same call.** It calls `await MKWrapper.chat(request)` in-process and gets a
  `ChatResult`. There is no HTTP hop; the API layer is optional.
- **Same failure semantics.** Timeouts, no-engine, and provider outages all
  surface as `ok=false` with a safe, printable message — a REPL can render the
  fallback instead of crashing.
- **Same suggestions.** `MKWrapper.suggestions(context)` returns the same
  actions a TUI can present as command hints.

This keeps a single behavioral spec across web and OS, and is why validation,
timeouts, and AI-failure handling live in the wrapper rather than in the web
layer.

---

## 6. Cross-cutting concerns

- **Observability.** The wrapper emits counters via `mk.observability.metrics`
  (`mk_wrapper_chat_total`, `mk_wrapper_success_total`,
  `mk_wrapper_failures_total{type=…}`) and structured logs keyed by
  `request_id`.
- **Security.** Chat routes require auth (`require_auth`). The wrapper never
  leaks internal diagnostics to users — `AIFailureInfo.detail` is for logs;
  `AIFailureInfo.message` is the only user-facing text.
- **Degraded mode.** When no LLM provider is configured, the engine still
  answers via `command_router`; `ChatResult.degraded` is `true` and the UI
  shows a "Limited mode" badge.

See [`ERROR_HANDLING.md`](./ERROR_HANDLING.md) for the full AI-failure taxonomy,
the error envelope, and the phased roadmap.
