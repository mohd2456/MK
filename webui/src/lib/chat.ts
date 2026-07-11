/**
 * Chat API
 * =========
 * Typed helpers for the conversational endpoints, layered on the shared
 * `api` client so auth, credentials, and error normalization are consistent.
 *
 * Backend contracts:
 *   - POST /api/v1/chat/message      -> ChatHttpResponse
 *   - GET  /api/v1/chat/suggestions  -> SuggestionsResponse
 *   - GET  /api/v1/chat/history      -> ChatHistoryResponse
 */

import { get, post } from "./api";
import { uuid } from "./utils";
import type {
  ChatContext,
  ChatHistoryResponse,
  ChatHttpResponse,
  SuggestionsResponse,
} from "@/types/chat";

const SESSION_KEY = "mk_chat_session_id";

/**
 * Return a stable per-browser chat session id, creating and persisting one on
 * first use. Falls back to an ephemeral id if localStorage is unavailable
 * (e.g. private mode) so chat still works.
 */
export function getChatSessionId(): string {
  try {
    let id = localStorage.getItem(SESSION_KEY);
    if (!id) {
      id = uuid();
      localStorage.setItem(SESSION_KEY, id);
    }
    return id;
  } catch {
    return uuid();
  }
}

/** Send a chat message and return the full, well-formed response envelope. */
export function sendChatMessage(
  content: string,
  context: ChatContext,
  sessionId?: string
): Promise<ChatHttpResponse> {
  return post<ChatHttpResponse>("/chat/message", {
    content,
    context,
    session_id: sessionId ?? getChatSessionId(),
  });
}

/** Build the suggestions endpoint path (also used as the SWR cache key). */
export function suggestionsKey(page: string, selection?: string): string {
  const params = new URLSearchParams({ page: page || "/" });
  if (selection) params.set("selection", selection);
  return `/chat/suggestions?${params.toString()}`;
}

/** Fetch context-aware suggestions for a page/selection. */
export function fetchSuggestions(
  page: string,
  selection?: string
): Promise<SuggestionsResponse> {
  return get<SuggestionsResponse>(suggestionsKey(page, selection));
}

/** Fetch persisted chat history for a session. */
export function fetchChatHistory(sessionId?: string): Promise<ChatHistoryResponse> {
  const id = sessionId ?? getChatSessionId();
  const params = new URLSearchParams({ session_id: id });
  return get<ChatHistoryResponse>(`/chat/history?${params.toString()}`);
}
