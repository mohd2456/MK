/**
 * MK OS Chat Types
 * =================
 * Types for chat messages, actions, context-aware suggestions, AI-failure
 * envelopes, and WebSocket events. These mirror the backend contracts in
 * `src/mk/web/app.py` (ChatResponse, SuggestionsResponse) and
 * `src/mk/wrapper/` (AIFailureType, SuggestedAction) so the UI stays type-safe
 * end to end.
 */

/** Chat message sender */
export type ChatRole = "user" | "assistant";

/**
 * Classification of an AI/engine failure, mirrors `mk.wrapper.errors.AIFailureType`
 * plus the `invalid_input` value the WebSocket path emits for bad client input.
 */
export type AIFailureType =
  | "timeout"
  | "engine_error"
  | "empty_output"
  | "malformed_output"
  | "schema_invalid"
  | "no_engine"
  | "provider_unavailable"
  | "invalid_input";

/** Action type for inline chat buttons */
export interface ChatAction {
  label: string;
  action: "navigate" | "api_call" | "copy";
  target?: string;
  method?: "GET" | "POST" | "PUT" | "DELETE";
  endpoint?: string;
  body?: Record<string, unknown>;
}

/**
 * A context-aware suggested action, mirrors `mk.wrapper.models.SuggestedAction`.
 * `command` is the text sent to the assistant when the suggestion is activated.
 */
export interface SuggestedAction {
  id: string;
  label: string;
  description: string;
  command: string;
  category: string;
  icon?: string | null;
}

/** A single chat message rendered in the panel */
export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  timestamp: string;
  actions?: ChatAction[];
  streaming?: boolean;
  /** False when this assistant message represents an AI/engine failure. */
  ok?: boolean;
  /** Failure classification when `ok` is false. */
  failureType?: AIFailureType | null;
  /** Whether retrying the request that produced this message may help. */
  retryable?: boolean;
  /** True when answered in a reduced-capability mode (e.g. no LLM configured). */
  degraded?: boolean;
  /** LLM provider that served the reply, if any. */
  provider?: string | null;
  /** The original user prompt that produced this reply (used for retry). */
  prompt?: string;
}

/** Context sent with each user message */
export interface ChatContext {
  page: string;
  selection?: string;
  selected_pool?: string;
  selected_container?: string;
  [key: string]: unknown;
}

/**
 * HTTP response envelope from `POST /api/v1/chat/message`.
 * Always well-formed: `ok` distinguishes success from an AI failure, and the
 * failure detail lives in the body (the request itself returns HTTP 200).
 */
export interface ChatHttpResponse {
  content: string;
  actions: ChatAction[];
  ok: boolean;
  failure_type: AIFailureType | null;
  retryable: boolean;
  degraded: boolean;
  provider: string | null;
  suggestions: SuggestedAction[];
  elapsed_ms: number;
}

/** Response from `GET /api/v1/chat/suggestions`. */
export interface SuggestionsResponse {
  page: string;
  suggestions: SuggestedAction[];
}

/** A single persisted history entry from `GET /api/v1/chat/history`. */
export interface ChatHistoryEntry {
  role: ChatRole;
  content: string;
  timestamp: string;
  ok?: boolean;
  failure_type?: AIFailureType | null;
  actions?: ChatAction[];
}

/** Response from `GET /api/v1/chat/history`. */
export interface ChatHistoryResponse {
  messages: ChatHistoryEntry[];
}

/** WebSocket message from client to server */
export interface ChatRequest {
  type: "chat_message";
  id: string;
  content: string;
  context: ChatContext;
  session_id?: string;
}

/** WebSocket full response from server */
export interface ChatResponse {
  type: "chat_response";
  id: string;
  reply_to: string;
  content: string;
  actions?: ChatAction[];
  ok?: boolean;
  failure_type?: AIFailureType | null;
  degraded?: boolean;
  provider?: string | null;
  suggestions?: SuggestedAction[];
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
