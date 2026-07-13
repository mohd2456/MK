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

import { ApiError, get, post } from "./api";
import { API_BASE } from "./constants";
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

/** Callbacks for consuming a streamed chat reply. */
export interface StreamCallbacks {
  /** Called with each text chunk as it arrives. */
  onToken: (chunk: string) => void;
  /** Called once when the stream completes normally. */
  onDone?: () => void;
  /** Called if the stream errors (network or server-signalled). */
  onError?: (error: unknown) => void;
}

/**
 * Stream a chat reply via Server-Sent Events (POST /api/v1/chat/stream).
 *
 * Reads the response body incrementally, parses `data: {json}` SSE frames,
 * and invokes `onToken` for each token as it arrives. Resolves with the full
 * accumulated text once the stream closes. Pass an `AbortSignal` to cancel.
 */
export async function streamChatMessage(
  content: string,
  context: ChatContext,
  opts: StreamCallbacks & { sessionId?: string; signal?: AbortSignal }
): Promise<string> {
  const { onToken, onDone, onError, sessionId, signal } = opts;
  let full = "";

  try {
    const response = await fetch(`${API_BASE}/chat/stream`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content,
        context,
        session_id: sessionId ?? getChatSessionId(),
      }),
      signal,
    });

    if (response.status === 401) {
      window.location.href = "/login";
      throw new ApiError(401, "Unauthorized");
    }
    if (!response.ok || !response.body) {
      throw new ApiError(response.status, response.statusText);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    // Read until the stream ends. SSE frames are separated by a blank line.
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const line = frame.trim();
        if (!line.startsWith("data:")) continue;
        const payload = line.slice(line.indexOf("data:") + 5).trim();
        try {
          const evt = JSON.parse(payload) as {
            type: string;
            content?: string;
            message?: string;
          };
          if (evt.type === "token" && evt.content) {
            full += evt.content;
            onToken(evt.content);
          } else if (evt.type === "done") {
            onDone?.();
          } else if (evt.type === "error") {
            onError?.(new Error(evt.message || "stream error"));
          }
        } catch {
          // Ignore malformed frames; keep consuming the stream.
        }
      }
    }

    return full;
  } catch (error) {
    onError?.(error);
    throw error;
  }
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
