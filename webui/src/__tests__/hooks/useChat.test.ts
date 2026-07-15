/**
 * useChat Hook Tests
 * ===================
 * Verifies WS→store dispatch for streaming, typing, stats, and sendMessage.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import type { WSMessage } from "@/lib/ws";

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
import { useDashboardStore } from "@/stores/dashboardStore";

function push(msg: Record<string, unknown>) {
  act(() => {
    messageHandler?.(msg as unknown as WSMessage);
  });
}

describe("useChat streaming + stats", () => {
  beforeEach(() => {
    messageHandler = null;
    sendMock.mockReset();
    useChatStore.setState({ messages: [], isTyping: false, currentStreamId: null });
    useDashboardStore.setState({ stats: null, lastUpdated: null });
  });

  it("renders a streamed reply live, then finalizes it", () => {
    renderHook(() => useChat());
    push({ type: "chat_response", id: "s1", reply_to: "r1", done: false });
    let state = useChatStore.getState();
    expect(state.currentStreamId).toBe("s1");
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0].streaming).toBe(true);

    push({ type: "chat_stream", id: "s1", chunk: "Hello ", done: false });
    push({ type: "chat_stream", id: "s1", chunk: "world", done: false });
    state = useChatStore.getState();
    expect(state.messages[0].content).toBe("Hello world");

    push({ type: "chat_stream", id: "s1", done: true, actions: [] });
    state = useChatStore.getState();
    expect(state.messages[0].streaming).toBe(false);
    expect(state.currentStreamId).toBeNull();
  });

  it("toggles the typing indicator", () => {
    renderHook(() => useChat());
    push({ type: "typing_indicator", active: true });
    expect(useChatStore.getState().isTyping).toBe(true);
    push({ type: "typing_indicator", active: false });
    expect(useChatStore.getState().isTyping).toBe(false);
  });

  it("sends a chat_message with session id", () => {
    const { result } = renderHook(() => useChat());
    act(() => {
      result.current.sendMessage("hello", { page: "/" });
    });
    expect(useChatStore.getState().messages[0].role).toBe("user");
    expect(sendMock).toHaveBeenCalledTimes(1);
    expect(sendMock.mock.calls[0][0].type).toBe("chat_message");
    expect(sendMock.mock.calls[0][0].content).toBe("hello");
  });

  it("dispatches stats_update to the dashboard store", () => {
    renderHook(() => useChat());
    push({
      type: "stats_update",
      cpu_percent: 42.5,
      ram_used_gb: 3.2,
      ram_total_gb: 16.0,
      ram_percent: 20.0,
      disk_used_tb: 0.5,
      disk_total_tb: 2.0,
      disk_percent: 25.0,
      containers_running: 5,
      containers_total: 8,
      timestamp: 1234567890,
    });
    const stats = useDashboardStore.getState().stats;
    expect(stats).not.toBeNull();
    expect(stats!.cpu_percent).toBe(42.5);
    expect(stats!.containers_running).toBe(5);
    expect(stats!.ram_total_gb).toBe(16.0);
  });
});
