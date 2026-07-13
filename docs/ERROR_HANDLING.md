# MK AI Assistant — Error Handling & AI-Failure Plan

AI systems fail in ways ordinary software does not: they time out, return
nothing, loop on a single token, or confidently emit invalid structured data.
MK's assistant is built so that **none of these break the experience**. This
document defines the failure taxonomy, how each failure is detected, logged,
and surfaced, the fallback behavior, the consistent error envelope shared by
every caller, and a phased roadmap for the remaining work.

Related: [`ARCHITECTURE.md`](./ARCHITECTURE.md).

---

## 1. Two classes of problems

MK draws a hard line between two kinds of problems (see
`src/mk/wrapper/errors.py`):

1. **Client errors** — the caller sent something invalid (empty message,
   oversized payload, wrong type). These are *raised* as
   `InputValidationError` so the transport can return the right status
   (**HTTP 422**). The wrapper did nothing wrong; the input was bad.

2. **AI / runtime failures** — the engine timed out, crashed, returned empty
   or degenerate output, produced invalid JSON, or no model is configured.
   These are **never raised** out of `MKWrapper.chat()`. They are captured,
   classified, logged, and returned inside a `ChatResult` with a safe,
   user-facing fallback message. This is what lets the assistant degrade
   gracefully instead of crashing.

> **Design rule:** `MKWrapper.chat()` raises **only** `InputValidationError`.
> Every other failure comes back as `ok = false` with a friendly message.

---

## 2. The AI-failure taxonomy

`AIFailureType` (`src/mk/wrapper/errors.py`). The string values are stable and
safe to expose to clients and to use as metric label values.

| Type | Meaning | Detected in | Retryable | HTTP status |
| --- | --- | --- | --- | --- |
| `none` | No failure — the response is trusted. | — | — | 200 |
| `timeout` | Engine did not respond within the deadline (60s). | `asyncio.wait_for` in `wrapper.py` | ✅ | 200 (`ok:false`) |
| `engine_error` | Engine raised an unexpected exception. | `except Exception` in `wrapper.py` | ❌ | 200 (`ok:false`) |
| `empty_output` | Engine returned empty / whitespace-only text. | `failures.detect_output_failure` | ✅ | 200 (`ok:false`) |
| `malformed_output` | Degenerate output (runaway repetition) — likely a loop/hallucination. | `failures.detect_output_failure` | ✅ | 200 (`ok:false`) |
| `schema_invalid` | JSON was requested but the output didn't parse/validate. | `failures.detect_output_failure` | ✅ | 200 (`ok:false`) |
| `no_engine` | No engine could be constructed or supplied. | `wrapper._get_engine` | ❌ | 200 (`ok:false`) |
| `provider_unavailable` | All configured LLM providers failed / none configured. | `wrapper._classify_exception` (`ProviderError`) | ✅ | 200 (`ok:false`) |

`HARD_FAILURES` (all types except `none`) mark responses where `ok = false`.

---

## 3. Detection, logging, and surfacing

For each failure the wrapper does three things: **detect** it at the right
layer, **log** it with the `request_id` (and increment a metric), and
**surface** a safe message to the user.

### 3.1 `timeout`
- **Detect:** `engine.process()` is wrapped in `asyncio.wait_for(timeout=60s)`.
- **Log:** `WARNING "Engine timed out after 60.0s (request_id=…)"`.
- **Surface:** "That took longer than expected… please try again." Marked
  `retryable = true`.

### 3.2 `engine_error` / `provider_unavailable`
- **Detect:** any exception from `engine.process()`. If it is a
  `mk.llm.base.ProviderError` it is classified `provider_unavailable`,
  otherwise `engine_error`.
- **Log:** `ERROR` with `exc_info=True` and the failure type + `request_id`.
- **Surface:** a generic "something went wrong, I've logged it" message. The
  exception text goes to `AIFailureInfo.detail` (logs only), never to the user.

### 3.3 `empty_output` / `malformed_output` / `schema_invalid`
- **Detect:** `failures.detect_output_failure(content, expects_json)` — a pure,
  side-effect-free function:
  - **empty:** blank/whitespace-only text.
  - **malformed:** heuristic repetition check on responses ≥ 200 chars (a single
    line > 60% of lines, or the top token > 50% of tokens).
  - **schema_invalid:** when `expects_json`, the text (after stripping code
    fences / surrounding prose) must `json.loads` successfully.
- **Log:** `WARNING "AI output failure (<type>) for request_id=…"`.
- **Surface:** a message that explicitly says the assistant withheld an
  unreliable answer, rather than passing off a hallucination as fact.

### 3.4 `no_engine`
- **Detect:** `_get_engine()` returns `None` (build attempted once, failed).
- **Log:** `ERROR "Failed to build MK engine: …"`.
- **Surface:** "MK is running, but its engine could not be started…"

### 3.5 Metrics
Every hard failure increments
`mk_wrapper_failures_total{type=<failure>}`; successes increment
`mk_wrapper_success_total`; all attempts increment `mk_wrapper_chat_total`.
This makes failure rates alertable per type.

---

## 4. Fallback behavior

- **Graceful degradation, never a crash.** A failure always yields a
  `ChatResult` with a safe `content`. The web UI renders it as a distinct,
  accessible **alert bubble** (`role="alert"`, `ChatBubble.tsx`) with a
  friendly per-type label — the conversation continues.
- **No-LLM (degraded) mode.** If no provider is configured, the engine still
  answers deterministic commands via `command_router`. `ChatResult.degraded`
  is `true` and the UI shows a **"Limited mode"** badge (not an error).
- **Client-side resilience.** If the network call itself fails (offline), the
  UI falls back to a local simulated response so the demo keeps working; a
  `4xx/5xx` (`ApiError`) is shown as a clear, non-breaking failure bubble.
- **Retryability.** `AIFailureInfo.retryable` tells clients whether a retry may
  help (`timeout`, `empty_output`, `malformed_output`, `schema_invalid`,
  `provider_unavailable`) versus not (`engine_error`, `no_engine`).

---

## 5. The consistent error envelope

Every caller receives the **same** shape. Internally that is `ChatResult`
(`src/mk/wrapper/models.py`); over HTTP it is `ChatResponse`; over WS it is a
`chat_response` frame; the TypeScript mirror is `ChatMessageResponse`
(`webui/src/types/chat.ts`).

### 5.1 HTTP success / AI-failure (both `200`)

```jsonc
// POST /api/v1/chat/message
{
  "content": "Your tank pool is healthy at 75% capacity…", // answer OR safe fallback
  "actions": [],                 // engine-produced inline actions
  "suggestions": [               // context-aware follow-ups (page-based)
    { "id": "snapshot", "label": "Snapshot tank",
      "prompt": "Create a snapshot of tank", "kind": "suggestion" }
  ],
  "ok": true,                    // false on any AI failure
  "degraded": false,             // true in no-LLM mode
  "llm_available": true,
  "failure_type": null,          // one of the AIFailureType values when ok=false
  "tokens_used": 128
}
```

### 5.2 HTTP client error (`422`)

```jsonc
// invalid input (e.g. empty content) — the ONLY error status chat returns
{ "detail": "content must not be empty" }
```

### 5.3 WebSocket frame

```jsonc
{
  "type": "chat_response",
  "id": "…", "reply_to": "…",
  "content": "…",
  "ok": false,
  "degraded": false,
  "failure_type": "timeout",
  "suggestions": [ … ],
  "done": true
}
```

**Field contract (must stay in sync):** `ok`, `content`, `failure_type`,
`degraded`, `llm_available`, `suggestions`, `actions`, `tokens_used`. The
frontend `ChatMessageResponse` / `SuggestedAction` / `AIFailureType` types
mirror these exactly.

---

## 6. Phased roadmap (remaining work + estimates)

Estimates assume one engineer and are ranges (calendar time), not commitments.
Phase 1 (typed wrapper + chat wiring) and this phase (context-aware UI + docs)
are **complete**.

| Phase | Goal | Key work | Estimate |
| --- | --- | --- | --- |
| **3 — Context-awareness depth** | Move beyond page→chips to *stateful* context. | Send selection/filter metadata (selected pool/container) in `PageContext.metadata`; wrapper enriches the engine prompt; ground answers in `memory/system_state`; per-page action `kind` (`command`/`navigation`) wired to real handlers. | **1–2 weeks** |
| **4 — OS integration PoC** | Prove the terminal path reuses the wrapper. | `mk-shell`/`chat.py` builds `ChatRequest` in-process; synthetic `PageContext` for TUI screens; render `ok=false` fallbacks in the REPL; shared history. | **2–3 weeks** |
| **5 — Plugin permission / security model** | Safe execution of assistant-triggered actions. | Capability manifests per plugin (`src/mk/plugins`, `src/mk/policy`); consent prompts for privileged/destructive actions; audit log of executed actions; sandbox boundaries. | **3–4 weeks** |
| **6 — Cross-platform** | Run beyond the reference Linux box. | Abstract OS calls behind adapters; validate on other distros/arch (Graviton/arm64); packaging for the appliance image (`os-build/`); CI matrix. | **3–5 weeks** |

**Ongoing / hardening (parallel to the above):**
- Streaming responses end-to-end (`chat_stream` frames already modeled).
- Retry-with-backoff for `retryable` failures behind a user-visible "Retry".
- Provider health checks feeding `provider_unavailable` proactively.
- Load/latency budgets and alerts on `mk_wrapper_failures_total{type}`.

---

## 7. Testing

- **Backend:** `tests/web/test_api_chat.py` (endpoint wiring, 422 on bad input,
  context actions) plus wrapper/failure unit tests. Run:
  `uv run python -m pytest tests/web/test_api_chat.py -q`.
- **Frontend:** vitest covers the store's failure metadata
  (`__tests__/stores/chatStore.test.ts`), the failure-aware bubble
  (`__tests__/components/ChatBubble.test.tsx`), and the suggestions wiring incl.
  loading/empty/error (`__tests__/components/ContextSuggestions.test.tsx`).
  Run: `cd webui && pnpm test`.
