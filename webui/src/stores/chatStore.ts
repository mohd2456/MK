/**
 * Chat Store
 * ===========
 * Manages chat messages, streaming state, and conversation context.
 * Persists across page navigation (chat panel stays active).
 */

import { create } from "zustand";
import type { AIFailureType, ChatMessage, ChatAction } from "@/types/chat";
import { uuid } from "@/lib/utils";

/** Optional AI-failure / provenance metadata attached to an assistant reply. */
export interface AssistantMeta {
  ok?: boolean;
  failureType?: AIFailureType | null;
  retryable?: boolean;
  degraded?: boolean;
  provider?: string | null;
  /** The user prompt that produced this reply, so a failed reply can be retried. */
  prompt?: string;
}

interface ChatState {
  messages: ChatMessage[];
  isTyping: boolean;
  currentStreamId: string | null;

  // Actions
  addUserMessage: (content: string) => string;
  addAssistantMessage: (
    id: string,
    content: string,
    actions?: ChatAction[],
    meta?: AssistantMeta
  ) => void;
  setMessages: (messages: ChatMessage[]) => void;
  startStream: (id: string, replyTo: string) => void;
  appendStreamChunk: (id: string, chunk: string) => void;
  endStream: (id: string, actions?: ChatAction[]) => void;
  setTyping: (typing: boolean) => void;
  clearHistory: () => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  isTyping: false,
  currentStreamId: null,

  addUserMessage: (content) => {
    const id = uuid();
    const message: ChatMessage = {
      id,
      role: "user",
      content,
      timestamp: new Date().toISOString(),
    };
    set((s) => ({ messages: [...s.messages, message] }));
    return id;
  },

  addAssistantMessage: (id, content, actions, meta) => {
    const message: ChatMessage = {
      id,
      role: "assistant",
      content,
      timestamp: new Date().toISOString(),
      actions,
      ok: meta?.ok ?? true,
      failureType: meta?.failureType ?? null,
      retryable: meta?.retryable ?? false,
      degraded: meta?.degraded ?? false,
      provider: meta?.provider ?? null,
      prompt: meta?.prompt,
    };
    set((s) => ({
      messages: [...s.messages, message],
      isTyping: false,
    }));
  },

  setMessages: (messages) => set({ messages }),

  startStream: (id, _replyTo) => {
    const message: ChatMessage = {
      id,
      role: "assistant",
      content: "",
      timestamp: new Date().toISOString(),
      streaming: true,
    };
    set((s) => ({
      messages: [...s.messages, message],
      currentStreamId: id,
      isTyping: false,
    }));
  },

  appendStreamChunk: (id, chunk) => {
    const { currentStreamId } = get();
    if (currentStreamId !== id) return;

    set((s) => ({
      messages: s.messages.map((msg) =>
        msg.id === id ? { ...msg, content: msg.content + chunk } : msg
      ),
    }));
  },

  endStream: (id, actions) => {
    set((s) => ({
      messages: s.messages.map((msg) =>
        msg.id === id ? { ...msg, streaming: false, actions } : msg
      ),
      currentStreamId: null,
    }));
  },

  setTyping: (typing) => set({ isTyping: typing }),

  clearHistory: () => set({ messages: [], currentStreamId: null, isTyping: false }),
}));
