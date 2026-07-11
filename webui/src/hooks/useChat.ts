/**
 * useChat Hook
 * =============
 * Manages the chat interaction over WebSocket.
 * Sends user messages, handles incoming responses and stream chunks,
 * and dispatches to the chatStore.
 */

import { useEffect, useCallback } from "react";
import { useWebSocket } from "./useWebSocket";
import { useChatStore } from "@/stores/chatStore";
import type { WSMessage } from "@/lib/ws";
import type { ChatContext, AIFailureType } from "@/types/chat";
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
  const { addUserMessage, startStream, appendStreamChunk, endStream, addAssistantMessage, setTyping } = useChatStore();

  // Handle incoming WebSocket messages related to chat
  useEffect(() => {
    const unsub = onMessage((msg: WSMessage) => {
      switch (msg.type) {
        case "chat_response": {
          const { id, reply_to, content, actions, done, ok, failure_type, degraded } =
            msg as WSMessage & {
              id: string;
              reply_to: string;
              content: string;
              actions?: Array<{ label: string; action: string; target?: string }>;
              done: boolean;
              ok?: boolean;
              failure_type?: AIFailureType;
              degraded?: boolean;
            };
          if (done) {
            // Thread AI-failure metadata through so the bubble can render a
            // graceful failure/degraded state instead of a plain reply.
            addAssistantMessage(id, content, actions as never, {
              ok: ok ?? true,
              failureType: failure_type ?? null,
              degraded: degraded ?? false,
            });
          } else {
            startStream(id, reply_to);
          }
          break;
        }
        case "chat_stream": {
          const { id, chunk, done, actions } = msg as WSMessage & {
            id: string;
            chunk: string;
            done: boolean;
            actions?: Array<{ label: string; action: string; target?: string }>;
          };
          if (done) {
            endStream(id, actions as never);
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
      }
    });

    return unsub;
  }, [onMessage, addAssistantMessage, startStream, appendStreamChunk, endStream, setTyping]);

  const sendMessage = useCallback(
    (content: string, context?: ChatContext) => {
      const messageId = addUserMessage(content);
      send({
        type: "chat_message",
        id: uuid(),
        reply_to: messageId,
        content,
        // `path` is the field the backend keys page-context off of.
        context: context ?? { path: window.location.pathname },
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
