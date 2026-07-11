# MK — Error Handling & AI-Failure Plan

MK's reliability goal is concrete and testable: **no unhandled exception ever
reaches the client, and every AI failure is detected, logged, and turned into a
calm, actionable message.** This document explains how that is achieved, the
failure taxonomy, the response envelope, and the phased roadmap for the
remaining work.

---

## 1. Two failure surfaces

The system draws a hard line between two very different kinds of "something
went wrong":

| | **Input validation error** | **AI failure** |
|---|---|---|
| Cause | The *caller* sent invalid data | The *AI/engine* misbehaved |
| Example | empty message, oversized payload | timeout, crash, hallucination |
| Representation | `InputValidationError` (raised) | `AIFailureType` (returned in body) |
| HTTP status | **422 Unprocessable Entity** | **200 OK** (detail in body) |
| Retry helps? | No — fix the input | Often yes (see `retryable`) |

Keeping these separate is what lets the wrapper promise "no 500s from the chat
path": the only exception it raises is the client's own fault, and it is mapped
to a 4xx. Everything else is data.

---

## 2. AI-failure taxonomy (`AIFailureType`)

Defined in `src/mk/wrapper/errors.py`. Each value is a stable string safe to
expose in API bodies and to key metrics on.

| Type | When it fires | How it's detected | Retryable | User-facing message (gist) |
|------|---------------|-------------------|:---------:|----------------------------|
| `timeout` | Engine exceeds the time budget | `asyncio.wait_for` raises `TimeoutError`; also `ProviderTimeout` | ✅ | "That took too long; please try again." |
| `engine_error` | Engine raises an unexpected exception | caught in `chat()` boundary | ✅ | "Something went wrong; it's been logged." |
| `empty_output` | Reply is missing/whitespace | `detect_empty_output` | ✅ | "I couldn't produce a response; rephrase?" |
| `malformed_output` | Runaway repetition / degenerate text | `detect_degenerate_output` | ✅ | "My response came back garbled; try again." |
| `schema_invalid` | JSON was expected but didn't parse/validate | `validate_structured_output` | ❌ | "Couldn't produce a valid result; stopped." |
| `no_engine` | No engine wired and none buildable | engine resolution returns `None` | ❌ | "AI isn't configured yet; use commands." |
| `provider_unavailable` | Every LLM provider failed | `ProviderError` from the LLM layer | ✅ | "No AI provider available right now." |

`malformed_output` and `schema_invalid` are the **hallucination signals**: the
model returned *something*, but it's either structurally degenerate (a loop) or
doesn't match the requested structure. Rather than pass unreliable data
downstream, the wrapper withholds it and returns a safe fallback.

---

## 3. Detection, logging, and fallback

### Detection
- **Timeouts** — every engine call runs under `asyncio.wait_for(timeout)`
  (default 60s, configurable per wrapper).
- **Exceptions** — a single `except Exception` boundary in `chat()` catches
  anything the engine throws and classifies it. LLM-layer `ProviderError` /
  `TimeoutError` are recognized and mapped to `provider_unavailable` / `timeout`.
- **Bad output** — after a *successful* return, `analyze_output` screens the
  text for empty, degenerate, and (when `expect_json=True`) schema-invalid
  content. These are the failures that don't raise.

### Logging (via `mk.observability`)
- Failures log at `ERROR` with the failure type and safe technical `detail`
  (and, for exceptions, a stack trace). Expected degraded states (`no_engine`)
  log at `INFO`, not `ERROR`.
- Metrics: `mk_wrapper_chat_total{outcome=...}`,
  `mk_wrapper_ai_failures_total{type=...}`, and `mk_wrapper_chat_seconds`.
  These make failure rates and latency visible on the existing `/metrics`
  Prometheus endpoint.
- User-facing text **never** contains stack traces, provider names, or raw
  exception strings — those stay in the logs.

### Fallback behavior
- Every failure yields a populated `ChatResult` with `ok=False`, a calm
  user-facing `message`, the `failure` detail, and — crucially — the same
  context-aware `suggestions` a success would carry, so the user always has a
  next step.
- `no_engine` additionally sets `degraded=True`, signalling the UI to show a
  "configure a provider" affordance while still allowing direct commands.

---

## 4. The response envelope

Both the HTTP and WebSocket chat paths return the same consistent shape:

```jsonc
{
  "content": "All storage pools are healthy.",  // reply OR calm fallback
  "ok": true,                                    // false on any AI failure
  "failure_type": null,                          // e.g. "timeout" when ok=false
  "retryable": false,                            // whether a retry may help
  "degraded": false,                             // true in reduced-capability mode
  "provider": "openai",                          // provider that served it, if any
  "actions": [],                                 // inline actions
  "suggestions": [                               // always present, context-aware
    { "id": "dash.status", "label": "System status", "command": "status", ... }
  ],
  "elapsed_ms": 42.1
}
```

Consumers can rely on: `ok` is always present; `content` is always a safe
string to display; `suggestions` is never empty. This lets the UI render AI
failures inline (a subtle notice + retry) instead of throwing an error screen.

---

## 5. Reliability boundaries elsewhere

The wrapper is the core of the chat path, but the broader app already applies
the same defensive posture:

- **Transport** — auth, per-IP rate limiting (with bounded memory), CORS, and a
  request-id middleware wrap every route.
- **Input sanitation** — shell-interpolated identifiers (service/container/pool
  names) are validated against a strict allowlist before use.
- **Suggestions never fail** — `get_suggestions` coerces bad context to a
  default rather than raising, so the UI's context panel can't break the page.

---

## 6. Phased roadmap

This phase delivered the AI/wrapper core (items ✅ below). The remaining phases
turn the prototype into the full product. Estimates assume a small team and are
deliberately realistic rather than optimistic.

| Phase | Scope | Est. |
|-------|-------|------|
| ✅ **0. AI/wrapper core** (this phase) | Typed `MKWrapper`, strict validation, timeout, exception isolation, AI-failure detection, chat wired end-to-end (HTTP + WS), context suggestions endpoint, docs, tests. | Done |
| **1. Context-awareness UI** | Wire the web UI's context panel + chat to the live endpoints; render AI-failure states inline with retry; page-aware shortcuts across all screens; accessibility pass. | ~2 wk |
| **2. Reliability hardening** | Retry-with-backoff for `retryable` failures; circuit-breaker per provider; persistent sessions/history via the SQLite store; structured audit trail. | ~1–2 wk |
| **3. OS-integration proof-of-concept** | Terminal/shell surface calling the same `MKWrapper`; systemd service wiring; a minimal on-device console. | ~2–3 wk |
| **4. Plugin permission & security model** | Capability-scoped plugin permissions, sandbox review, signed plugins, secure defaults for third-party extensions. | ~2–3 wk |
| **5. Cross-platform & polish** | Consistent APIs across major OSes/browsers, packaging, low-footprint tuning, load/perf testing against defined targets. | ~2–3 wk |

**Full remaining effort: ~9–14 weeks** for a small team, landing incrementally
so each phase is usable on its own.

---

## 7. How this is verified

- Unit tests assert each `AIFailureType` is produced for its trigger
  (`tests/wrapper/test_wrapper.py`, `test_failures.py`).
- Integration tests assert the chat endpoint returns **200 with `ok=false`**
  (not 500) for engine errors and no-engine, and **422** for invalid input
  (`tests/web/test_api_chat.py`).
- Metrics/logging are emitted on every path so failure rates are observable in
  production, not just in tests.
