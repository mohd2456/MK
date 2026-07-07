/**
 * MK OS Chat Types
 * =================
 * Types for chat messages, actions, and WebSocket events.
 */

/** Chat message sender */
export type ChatRole = "user" | "assistant";

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
}

/** Context sent with each user message */
export interface ChatContext {
  page: string;
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
