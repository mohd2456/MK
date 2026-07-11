/**
 * Chat Store Tests
 * =================
 * Tests for the Zustand chat store: messages, streaming, typing indicators.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { useChatStore } from "@/stores/chatStore";

describe("chatStore", () => {
  beforeEach(() => {
    useChatStore.setState({
      messages: [],
      isTyping: false,
      currentStreamId: null,
    });
  });

  it("starts with empty messages", () => {
    const state = useChatStore.getState();
    expect(state.messages).toHaveLength(0);
    expect(state.isTyping).toBe(false);
    expect(state.currentStreamId).toBeNull();
  });

  it("adds a user message and returns its id", () => {
    const store = useChatStore.getState();
    const id = store.addUserMessage("Hello MK");

    const state = useChatStore.getState();
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0].id).toBe(id);
    expect(state.messages[0].role).toBe("user");
    expect(state.messages[0].content).toBe("Hello MK");
    expect(state.messages[0].timestamp).toBeDefined();
  });

  it("adds an assistant message", () => {
    const store = useChatStore.getState();
    store.addAssistantMessage("msg-1", "Hi there!", [
      { label: "View details", action: "navigate", target: "/storage" },
    ]);

    const state = useChatStore.getState();
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0].role).toBe("assistant");
    expect(state.messages[0].content).toBe("Hi there!");
    expect(state.messages[0].actions).toHaveLength(1);
    expect(state.messages[0].actions![0].label).toBe("View details");
  });

  it("manages typing indicator", () => {
    const store = useChatStore.getState();

    store.setTyping(true);
    expect(useChatStore.getState().isTyping).toBe(true);

    store.setTyping(false);
    expect(useChatStore.getState().isTyping).toBe(false);
  });

  it("starts a stream and appends chunks", () => {
    const store = useChatStore.getState();

    store.startStream("stream-1", "user-msg-1");

    let state = useChatStore.getState();
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0].streaming).toBe(true);
    expect(state.messages[0].content).toBe("");
    expect(state.currentStreamId).toBe("stream-1");

    store.appendStreamChunk("stream-1", "Hello ");
    store.appendStreamChunk("stream-1", "world!");

    state = useChatStore.getState();
    expect(state.messages[0].content).toBe("Hello world!");
  });

  it("ends a stream and sets actions", () => {
    const store = useChatStore.getState();

    store.startStream("stream-1", "user-msg-1");
    store.appendStreamChunk("stream-1", "Response text");
    store.endStream("stream-1", [
      { label: "Do something", action: "api_call", method: "POST", endpoint: "/test" },
    ]);

    const state = useChatStore.getState();
    expect(state.messages[0].streaming).toBe(false);
    expect(state.messages[0].actions).toHaveLength(1);
    expect(state.currentStreamId).toBeNull();
  });

  it("ignores chunks for wrong stream id", () => {
    const store = useChatStore.getState();

    store.startStream("stream-1", "user-msg-1");
    store.appendStreamChunk("wrong-id", "should be ignored");

    const state = useChatStore.getState();
    expect(state.messages[0].content).toBe("");
  });

  it("clears all history", () => {
    const store = useChatStore.getState();

    store.addUserMessage("Message 1");
    store.addAssistantMessage("msg-2", "Reply 1");
    store.addUserMessage("Message 2");

    expect(useChatStore.getState().messages).toHaveLength(3);

    store.clearHistory();

    const state = useChatStore.getState();
    expect(state.messages).toHaveLength(0);
    expect(state.currentStreamId).toBeNull();
    expect(state.isTyping).toBe(false);
  });

  it("adds assistant message and clears typing", () => {
    const store = useChatStore.getState();

    store.setTyping(true);
    store.addAssistantMessage("msg-1", "Response");

    const state = useChatStore.getState();
    expect(state.isTyping).toBe(false);
  });

  it("defaults assistant messages to a trusted (ok) non-degraded state", () => {
    const store = useChatStore.getState();
    store.addAssistantMessage("msg-1", "All good");

    const msg = useChatStore.getState().messages[0];
    expect(msg.ok).toBe(true);
    expect(msg.failureType).toBeNull();
    expect(msg.degraded).toBe(false);
  });

  it("stores AI-failure metadata on assistant messages", () => {
    const store = useChatStore.getState();
    store.addAssistantMessage("msg-1", "Fallback text", [], {
      ok: false,
      failureType: "timeout",
      degraded: false,
    });

    const msg = useChatStore.getState().messages[0];
    expect(msg.ok).toBe(false);
    expect(msg.failureType).toBe("timeout");
  });

  it("stores degraded (no-LLM) metadata on assistant messages", () => {
    const store = useChatStore.getState();
    store.addAssistantMessage("msg-1", "Command-only reply", [], {
      ok: true,
      degraded: true,
    });

    const msg = useChatStore.getState().messages[0];
    expect(msg.ok).toBe(true);
    expect(msg.degraded).toBe(true);
  });
});
