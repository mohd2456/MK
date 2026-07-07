/**
 * Chat Store
 * ===========
 * Manages chat messages, streaming state, and conversation context.
 * Persists across page navigation (chat panel stays active).
 */

import { create } from "zustand";
import type { ChatMessage, ChatAction } from "@/types/chat";
import { uuid } from "@/lib/utils";

interface ChatState {
  messages: ChatMessage[];
  isTyping: boolean;
  currentStreamId: string | null;

  // Actions
  addUserMessage: (content: string) => string;
  addAssistantMessage: (id: string, content: string, actions?: ChatAction[]) => void;
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

  addAssistantMessage: (id, content, actions) => {
    const message: ChatMessage = {
      id,
      role: "assistant",
      content,
      timestamp: new Date().toISOString(),
      actions,
    };
    set((s) => ({
      messages: [...s.messages, message],
      isTyping: false,
    }));
  },

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
