/**
 * useChat Hook
 * =============
 * Manages the chat interaction over WebSocket.
 * Sends user messages, handles incoming responses and stream chunks,
 * and dispatches to the chatStore.
 *
 * Kept consistent with the HTTP path (`lib/chat.ts`): it sends the persistent
 * session id and threads the AI-failure envelope (ok/failure_type/degraded/
 * retryable) through to the store so failures render correctly.
 */

import { useEffect, useCallback, useRef } from "react";
import { useWebSocket } from "./useWebSocket";
import { useChatStore } from "@/stores/chatStore";
import { useDashboardStore } from "@/stores/dashboardStore";
import type { WSMessage } from "@/lib/ws";
import type { AIFailureType, ChatAction, ChatContext } from "@/types/chat";
import { getChatSessionId } from "@/lib/chat";
import { uuid } from "@/lib/utils";

interface UseChatReturn {
  /** Send a user chat message with optional page context */
  sendMessage: (content: string, context?: ChatContext) => void;
  /** Whether the WebSocket is connected */
  isConnected: boolean;
  /** Current WebSocket connection state */
  connectionState: string;
}

export function useChat(): UseChatReturn {
  const { send, onMessage, isConnected, connectionState } = useWebSocket();
  const {
    addUserMessage,
    startStream,
    appendStreamChunk,
    endStream,
    addAssistantMessage,
    setTyping,
  } = useChatStore();
  const { applyStatsUpdate } = useDashboardStore();

  // Maps an outgoing message id -> the prompt that produced it, so a failed
  // reply can offer a retry with the original text.
  const pendingPrompts = useRef<Map<string, string>>(new Map());

  // Handle incoming WebSocket messages related to chat
  useEffect(() => {
    const unsub = onMessage((msg: WSMessage) => {
      switch (msg.type) {
        case "chat_response": {
          const m = msg as WSMessage & {
            id: string;
            reply_to: string;
            content: string;
            actions?: ChatAction[];
            ok?: boolean;
            failure_type?: AIFailureType | null;
            retryable?: boolean;
            degraded?: boolean;
            provider?: string | null;
            done: boolean;
          };
          if (m.done) {
            const prompt = pendingPrompts.current.get(m.reply_to);
            pendingPrompts.current.delete(m.reply_to);
            addAssistantMessage(m.id, m.content, m.actions ?? [], {
              ok: m.ok ?? true,
              failureType: m.failure_type ?? null,
              retryable: m.retryable ?? false,
              degraded: m.degraded ?? false,
              provider: m.provider ?? null,
              prompt,
            });
          } else {
            startStream(m.id, m.reply_to);
          }
          break;
        }
        case "chat_stream": {
          const { id, chunk, done, actions } = msg as WSMessage & {
            id: string;
            chunk: string;
            done: boolean;
            actions?: ChatAction[];
          };
          if (done) {
            endStream(id, actions);
          } else {
            appendStreamChunk(id, chunk);
          }
          break;
        }
        case "typing_indicator": {
          const { active } = msg as WSMessage & { active: boolean };
          setTyping(active ?? true);
          break;
        }
        case "stats_update": {
          // Live dashboard stats pushed by the server every ~5s.
          applyStatsUpdate(msg as any);
          break;
        }
      }
    });

    return unsub;
  }, [onMessage, addAssistantMessage, startStream, appendStreamChunk, endStream, setTyping, applyStatsUpdate]);

  const sendMessage = useCallback(
    (content: string, context?: ChatContext) => {
      addUserMessage(content);
      const id = uuid();
      pendingPrompts.current.set(id, content);
      send({
        type: "chat_message",
        id,
        content,
        context: context ?? { page: window.location.pathname },
        session_id: getChatSessionId(),
      });
    },
    [send, addUserMessage]
  );

  return {
    sendMessage,
    isConnected,
    connectionState,
  };
}
