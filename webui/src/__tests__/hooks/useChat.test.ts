/**
 * useChat Hook Tests
 * ===================
 * Verifies that streaming WebSocket frames from the backend are dispatched into
 * the chat store as a live-growing assistant message, then finalized — the
 * live-streaming UX the chat panel renders.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import type { WSMessage } from "@/lib/ws";

// Capture the message handler registered by useChat so tests can push frames.
let messageHandler: ((msg: WSMessage) => void) | null = null;
const sendMock = vi.fn();

vi.mock("@/hooks/useWebSocket", () => ({
  useWebSocket: () => ({
    send: sendMock,
    onMessage: (h: (msg: WSMessage) => void) => {
      messageHandler = h;
      return () => {};
    },
    isConnected: true,
    connectionState: "connected",
  }),
}));

import { useChat } from "@/hooks/useChat";
import { useChatStore } from "@/stores/chatStore";

function push(msg: Record<string, unknown>) {
  act(() => {
    messageHandler?.(msg as unknown as WSMessage);
  });
}

describe("useChat streaming", () => {
  beforeEach(() => {
    messageHandler = null;
    sendMock.mockReset();
    useChatStore.setState({ messages: [], isTyping: false, currentStreamId: null });
  });

  it("renders a streamed reply live, then finalizes it", () => {
    renderHook(() => useChat());
    expect(messageHandler).toBeTruthy();

    // Backend opens the stream (chat_response with done:false).
    push({ type: "chat_response", id: "s1", reply_to: "r1", done: false });
    let state = useChatStore.getState();
    expect(state.currentStreamId).toBe("s1");
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0].streaming).toBe(true);

    // Tokens arrive and the bubble grows live.
    push({ type: "chat_stream", id: "s1", chunk: "Restarting ", done: false });
    push({ type: "chat_stream", id: "s1", chunk: "Plex.", done: false });
    state = useChatStore.getState();
    expect(state.messages[0].content).toBe("Restarting Plex.");
    expect(state.messages[0].streaming).toBe(true);

    // Stream closes and the bubble is finalized.
    push({ type: "chat_stream", id: "s1", done: true, actions: [] });
    state = useChatStore.getState();
    expect(state.messages[0].streaming).toBe(false);
    expect(state.currentStreamId).toBeNull();
  });

  it("toggles the typing indicator from WS frames", () => {
    renderHook(() => useChat());
    push({ type: "typing_indicator", active: true });
    expect(useChatStore.getState().isTyping).toBe(true);
    push({ type: "typing_indicator", active: false });
    expect(useChatStore.getState().isTyping).toBe(false);
  });

  it("sends a chat_message with session id when sendMessage is called", () => {
    const { result } = renderHook(() => useChat());
    act(() => {
      result.current.sendMessage("hello", { page: "/" });
    });
    // User message added locally + a chat_message frame sent over WS.
    expect(useChatStore.getState().messages[0].role).toBe("user");
    expect(sendMock).toHaveBeenCalledTimes(1);
    const sent = sendMock.mock.calls[0][0];
    expect(sent.type).toBe("chat_message");
    expect(sent.content).toBe("hello");
    expect(sent.session_id).toBeTruthy();
  });
});
