/**
 * MK OS Chat Types
 * =================
 * Types for chat messages, actions, and WebSocket events.
 *
 * The request/response shapes below mirror the backend contract in
 * `src/mk/wrapper/models.py` and the `/api/v1/chat/*` endpoints in
 * `src/mk/web/app.py`. Keep them in sync when the backend changes.
 */

/** Chat message sender */
export type ChatRole = "user" | "assistant";

/**
 * AI/engine failure classification, mirrors `mk.wrapper.errors.AIFailureType`.
 * `null` means no failure (a trusted response).
 */
export type AIFailureType =
  | "timeout"
  | "engine_error"
  | "empty_output"
  | "malformed_output"
  | "schema_invalid"
  | "no_engine"
  | "provider_unavailable"
  | null;

/** How a context-aware suggested action should be rendered. */
export type SuggestedActionKind = "suggestion" | "command" | "navigation";

/**
 * A context-aware suggested action, mirrors `mk.wrapper.models.SuggestedAction`.
 * `label` is the short visible text; `prompt` is what gets sent to the assistant.
 */
export interface SuggestedAction {
  id: string;
  label: string;
  prompt: string;
  kind: SuggestedActionKind;
}

/**
 * Response of `GET /api/v1/chat/suggestions`, mirrors
 * `SuggestionsResponse` in the backend.
 */
export interface SuggestionsResponse {
  path: string;
  context_label: string;
  suggestions: SuggestedAction[];
}

/**
 * Response of `POST /api/v1/chat/message`, mirrors `ChatResponse` in the
 * backend. On an AI failure `ok` is `false` and `failure_type` classifies it,
 * while `content` still holds a safe, user-facing fallback message.
 */
export interface ChatMessageResponse {
  content: string;
  actions: ChatAction[];
  suggestions: SuggestedAction[];
  ok: boolean;
  degraded: boolean;
  llm_available: boolean;
  failure_type: AIFailureType;
  tokens_used: number;
}

/** Action type for inline chat buttons */
export interface ChatAction {
  label: string;
  action: "navigate" | "api_call" | "copy";
  target?: string;
  method?: "GET" | "POST" | "PUT" | "DELETE";
  endpoint?: string;
  body?: Record<string, unknown>;
}

/** A single chat message */
export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  timestamp: string;
  actions?: ChatAction[];
  streaming?: boolean;
  /** False when the assistant reply is an AI-failure fallback (not trusted). */
  ok?: boolean;
  /** Failure classification when `ok` is false, for surfacing to the user. */
  failureType?: AIFailureType;
  /** True when the assistant is running without an LLM (limited mode). */
  degraded?: boolean;
}

/**
 * Context sent with each user message so the assistant can be page-aware.
 * `path` is the current route and is what the backend keys off
 * (`PageContext.from_raw`); `label` is an optional human-readable screen name.
 */
export interface ChatContext {
  path: string;
  label?: string;
  selected_pool?: string;
  selected_container?: string;
  [key: string]: unknown;
}

/** WebSocket message from client to server */
export interface ChatRequest {
  type: "chat_message";
  id: string;
  content: string;
  context: ChatContext;
}

/** WebSocket full response from server */
export interface ChatResponse {
  type: "chat_response";
  id: string;
  reply_to: string;
  content: string;
  actions?: ChatAction[];
  done: boolean;
}

/** WebSocket streaming chunk from server */
export interface ChatStreamChunk {
  type: "chat_stream";
  id: string;
  reply_to: string;
  chunk: string;
  done: boolean;
  actions?: ChatAction[];
}

/** System event push from server */
export interface SystemEvent {
  type: "alert" | "metric_update" | "job_complete" | "container_event" | "typing_indicator";
  [key: string]: unknown;
}
