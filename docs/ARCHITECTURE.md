# MK AI Assistant — Architecture

This document describes how the conversational AI assistant is put together:
the layers a request passes through, where responsibility lives, and how the
**MK wrapper** ties the web surface to the engine while keeping every path
defensive and testable.

> Scope: this covers the AI/wrapper core **plus** the now-connected web UI
> (context-aware suggestions, AI-failure rendering) and persistent, session-
> keyed chat history. Later phases (OS-integration proof-of-concept, plugin
> permission model, cross-platform packaging) are listed under
> [Roadmap](./ERROR_HANDLING.md#phased-roadmap) in the error-handling doc.

---

## 1. Layered overview

```
                    ┌──────────────────────────────────────────────┐
   Browser / OS     │  Web UI (React)   •   Terminal / OS shell     │
   surfaces         └───────────────┬──────────────────┬───────────┘
                                    │ HTTP / WebSocket  │ direct call
                                    ▼                   ▼
                    ┌──────────────────────────────────────────────┐
   Web API          │  FastAPI app  (src/mk/web/app.py)             │
   (transport)      │   • auth, rate limiting, CORS, observability  │
                    │   • /api/v1/chat/message   (POST)             │
                    │   • /api/v1/chat/suggestions (GET)            │
                    │   • /api/v1/chat/history   (GET, by session)  │
                    │   • /ws/chat               (WebSocket)        │
                    │   • ChatHistoryStore (SQLite persistence)     │
                    └───────────────────────┬──────────────────────┘
                                            │  ChatRequest (dict)
                                            ▼
                    ┌──────────────────────────────────────────────┐
   Wrapper          │  MKWrapper  (src/mk/wrapper/)                 │
   (the contract)   │   • validate input      (models.py)          │
                    │   • enforce timeout      (wrapper.py)         │
                    │   • isolate exceptions   (errors.py)          │
                    │   • detect AI failures   (failures.py)        │
                    │   • attach suggestions   (context.py)         │
                    │   • log + meter          (observability)      │
                    └───────────────────────┬──────────────────────┘
                                            │  engine.process(str)
                                            ▼
                    ┌──────────────────────────────────────────────┐
   Engine           │  MKEngine / MKEngineV2 (src/mk/core/)         │
   (intelligence)   │   • command router → direct tools            │
                    │   • agent loop → LLM reasoning + tools        │
                    │   • planner, policy, semantic memory (V2)     │
                    └───────┬───────────────────────┬──────────────┘
                            ▼                       ▼
                    ┌───────────────┐      ┌────────────────────────┐
   Providers /      │ LLM Router    │      │ Tools / Server managers │
   capabilities     │ (src/mk/llm/) │      │ (src/mk/server, ops...) │
                    │ multi-provider│      │ storage, docker, net... │
                    │ + fallback    │      └────────────────────────┘
                    └───────────────┘
```

The key architectural decision: **all conversational traffic goes through
`MKWrapper`.** The transport layer never calls `engine.process` directly, and
the engine never has to worry about HTTP concerns. This single choke point is
what makes "no unhandled crash" and "handle every AI error" achievable and
verifiable.

---

## 2. The MK wrapper (`src/mk/wrapper/`)

The wrapper is a small, focused package. Each module has one job:

| Module | Responsibility |
|--------|----------------|
| `models.py` | Typed, strictly-validated I/O contracts: `PageContext`, `ChatRequest`, `SuggestedAction`, `AIFailureInfo`, `ChatResult`. |
| `errors.py` | The `AIFailureType` taxonomy, user-facing fallback messages, and `InputValidationError` (the only exception the wrapper raises). |
| `failures.py` | Pure detectors for empty / degenerate / schema-invalid output. |
| `context.py` | Data-driven page → suggested-actions mapping (longest-prefix match). |
| `wrapper.py` | `MKWrapper` — orchestrates validation, timeout, exception isolation, failure screening, suggestions, and observability. |

### 2.1 Design principles

- **One choke point.** Web, WebSocket, and future OS/terminal callers all use
  the same `MKWrapper.chat()`, so behavior is identical everywhere.
- **Two failure surfaces, cleanly separated.** Invalid *caller* input raises
  `InputValidationError` (→ HTTP 422). Everything that can go wrong on the
  *AI/engine* side is caught and returned as a non-ok `ChatResult` — never
  raised. See [ERROR_HANDLING.md](./ERROR_HANDLING.md).
- **Duck-typed engine.** The wrapper only needs an object with an awaitable
  (or sync) `process(str)` returning something with `final_response` (or a
  bare string). This keeps it decoupled from `MKEngine`/`MKEngineV2` and makes
  it trivial to test with fakes — no real LLM required.
- **Lazy construction.** An `engine_factory` (sync or async) can defer engine
  creation until first use; a failing factory degrades to `NO_ENGINE` rather
  than crashing app startup.

### 2.2 Integration points

```python
from mk.wrapper import MKWrapper, ChatRequest

# Eager engine (web app does this in create_app):
wrapper = MKWrapper(engine=mk_engine)

# Or lazy/deferred:
wrapper = MKWrapper(engine_factory=build_engine, timeout=60)

result = await wrapper.chat(ChatRequest(content="status", context={"page": "/dashboard"}))
result.ok            # bool
result.content       # reply text OR a calm fallback message
result.failure_type  # None on success, else e.g. "timeout"
result.suggestions   # context-aware SuggestedAction list
```

The same object serves suggestions synchronously:

```python
wrapper.get_suggestions({"page": "/apps", "selection": "plex"})
```

---

## 3. Request lifecycle (chat)

1. **Transport.** `POST /api/v1/chat/message` authenticates (session cookie or
   bearer token), rate-limits per IP, and assigns a request id
   (`RequestIDMiddleware`).
2. **Adapt.** The endpoint builds a plain dict `{content, session_id, context,
   expect_json}` and hands it to `MKWrapper.chat()`. Validation is *not* done
   in the endpoint — it is centralized in the wrapper.
3. **Validate.** The wrapper coerces the dict into a `ChatRequest`. Empty /
   oversized content or a bad session id raises `InputValidationError`, which
   the endpoint maps to **HTTP 422**. The engine is never invoked for invalid
   input.
4. **Suggestions.** The `PageContext` is resolved to a suggestion list up front
   so even a failure response carries useful next actions.
5. **Invoke under budget.** `engine.process(content)` runs inside
   `asyncio.wait_for(timeout)`. A hung provider becomes a `TIMEOUT` result, not
   a hung request.
6. **Screen output.** On a normal return, the reply text is screened by
   `analyze_output` for empty / degenerate / schema-invalid content
   (hallucination signals). A detected problem becomes a non-ok result.
7. **Envelope.** The `ChatResult` is converted to the API `ChatResponse`
   (`ok`, `content`, `failure_type`, `retryable`, `degraded`, `provider`,
   `suggestions`, `elapsed_ms`) and returned with HTTP 200 (even for AI
   failures — the failure detail lives in the body, not the status code).
8. **Persist.** If the request carried a `session_id`, the user message and the
   assistant reply (including `ok`/`failure_type`) are appended to the
   `ChatHistoryStore` (best-effort — a storage error is logged and never breaks
   the response).
9. **Observe.** Every outcome increments metrics (`mk_wrapper_chat_total`,
   `mk_wrapper_ai_failures_total`) and emits a structured log line.

The WebSocket path (`/ws/chat`) follows the identical steps 2–9, emitting the
same fields inside a `chat_response` frame.

---

## 4. Context-awareness flow

`context.py` holds a declarative route → actions table. `get_suggestions`
resolves the current `PageContext.page` by **longest matching prefix**, so:

- `/dashboard` → dashboard actions (status, alerts, health)
- `/apps/containers` → inherits `/apps` actions (containers, restart)
- an unknown page → a generic fallback set (status, help)
- when `selection` is set (e.g. a container), an "Inspect &lt;selection&gt;"
  action is prepended.

Because each `SuggestedAction` carries a `command` string, the UI can make a
suggestion self-executing: activating it simply sends that command back through
`/api/v1/chat/message`. The web UI consumes `GET /api/v1/chat/suggestions` to
render page-aware shortcuts, and includes the current page in each chat request
so answers are context-aware end to end.

---

## 5. Web UI integration (`webui/`)

The React UI is now wired to the live endpoints (no more simulated data):

- **Types (`src/types/chat.ts`).** Mirror the backend contracts —
  `AIFailureType`, `SuggestedAction`, `ChatHttpResponse`, `SuggestionsResponse`,
  and the history shapes — so the UI is type-safe against the API.
- **API layer (`src/lib/chat.ts`, `src/hooks/useApi.ts`).** `sendChatMessage`,
  `fetchSuggestions`/`useChatSuggestions` (SWR), and `fetchChatHistory` all go
  through the shared `api` client (auth, credentials, error normalization).
  `getChatSessionId` mints and persists a per-browser session id in
  `localStorage`.
- **Context suggestions (`components/chat/ContextSuggestions.tsx`).** Fetches
  `/chat/suggestions` for the current route, shows a loading skeleton, and
  falls back to a built-in static set if the backend is unreachable — so the
  panel is never empty. Activating a chip sends its `command`.
- **Chat panel (`components/layout/ChatPanel.tsx`).** Sends the current page as
  context with every message, restores persisted history on mount, and renders
  the response envelope. On a transport failure it shows an honest error (with
  Retry) rather than fabricating an answer.
- **Message rendering (`components/chat/ChatBubble.tsx`).** A non-ok reply is
  styled as an alert with a short failure label; retryable failures get a Retry
  button; a successful-but-`degraded` reply shows a subtle "limited mode" note.

### Persistent chat history (`src/mk/web/chat_history.py`)

`ChatHistoryStore` is a small aiosqlite-backed store keyed by `session_id`. It
keeps a single long-lived connection (so the default in-memory database is
durable for the process lifetime; set `MK_CHAT_DB` to a file path for
cross-restart durability), bounds each session's history, and exposes
`append` / `get_messages` / `clear` / `close`. The web layer persists each
exchange best-effort and serves it back via `GET /api/v1/chat/history?session_id=…`,
so a browser reload restores the conversation.

---

## 6. The engine (`src/mk/core/`) — unchanged by this work

The wrapper deliberately does **not** modify engine behavior. The engine keeps
its existing two-track design:

- **Direct commands.** `CommandRouter` maps simple inputs (e.g. `status`,
  `containers`) straight to tools — fast, deterministic, no LLM needed.
- **Agent loop.** Complex requests go through `AgentLoop`, which builds context,
  calls the `LLMRouter` (multi-provider with health-based fallback), parses tool
  calls, executes them, and iterates up to a bounded number of steps.
- **No-LLM mode.** When no provider is configured, the engine still answers a
  useful subset via keyword routing and help text. The wrapper surfaces this as
  a successful-but-`degraded` result.

`MKEngineV2` adds plugins, a task planner, proactive ops, semantic memory, and a
policy engine — all transparent to the wrapper thanks to the shared `process`
interface.

---

## 7. Testing strategy

Backend (pytest):

- **Wrapper unit tests** (`tests/wrapper/`) exercise validation, timeout,
  engine/provider exceptions, output screening, lazy factories, and context
  mapping using in-memory `FakeEngine`/`FakeResponse` doubles — fully offline,
  no real LLM.
- **API integration tests** (`tests/web/test_api_chat.py`) drive the real
  FastAPI app via an ASGI client: success, empty→422, no-engine graceful
  degradation, engine-error-without-500, and the suggestions endpoint.
- **History tests** (`tests/web/test_chat_history.py`) cover the
  `ChatHistoryStore` (ordering, failure/action round-trip, pruning, isolation,
  idempotent close) and end-to-end persistence via the message/history
  endpoints. A shared autouse fixture closes the store after each test so no
  connection threads leak.

Frontend (vitest):

- **`ChatBubble.test.tsx`** — success, AI-failure alert + label, retry
  affordance, and the degraded note.
- **`ContextSuggestions.test.tsx`** — backend-driven chips (mocked SWR hook),
  activation sends the `command`, static fallback on error, loading skeleton.
- **`lib/chat.test.ts`** — session-id persistence, suggestion-key building, and
  that the typed helpers call the shared client with the right shapes.

This split keeps the fast, exhaustive logic tests separate from the slower
end-to-end wiring tests, and guarantees the "never crashes / handles every AI
error" properties are checked, not just asserted in prose.
