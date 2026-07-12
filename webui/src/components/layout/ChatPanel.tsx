/**
 * ChatPanel Component
 * ====================
 * Right sidebar chat panel. Always available, persists across pages.
 *
 * Design specs:
 * - Width: 384px (w-96)
 * - Collapsible via toggle button or Ctrl+/
 * - Independent scroll from main content
 * - Context-aware suggestions at the bottom
 */

import { useRef, useEffect, useCallback } from "react";
import { useLocation } from "react-router-dom";
import { Minus, X } from "lucide-react";
import { cn, uuid } from "@/lib/utils";
import { useUIStore } from "@/stores/uiStore";
import { useChatStore } from "@/stores/chatStore";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChatBubble } from "@/components/chat/ChatBubble";
import { ChatInput } from "@/components/chat/ChatInput";
import { TypingIndicator } from "@/components/chat/TypingIndicator";
import { ContextSuggestions } from "@/components/chat/ContextSuggestions";
import { sendChatMessage, fetchChatHistory } from "@/lib/chat";
import type { ChatContext, ChatMessage } from "@/types/chat";

export function ChatPanel() {
  const { chatOpen, setChatOpen } = useUIStore();
  const { messages, isTyping, addUserMessage, setTyping, addAssistantMessage, setMessages } =
    useChatStore();
  const scrollRef = useRef<HTMLDivElement>(null);
  const location = useLocation();
  const historyLoaded = useRef(false);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isTyping]);

  // Load persisted history once, on first mount, if the panel is empty.
  useEffect(() => {
    if (historyLoaded.current) return;
    historyLoaded.current = true;
    let cancelled = false;
    (async () => {
      try {
        const history = await fetchChatHistory();
        if (cancelled || history.messages.length === 0) return;
        if (useChatStore.getState().messages.length > 0) return;
        const restored: ChatMessage[] = history.messages.map((m) => ({
          id: uuid(),
          role: m.role,
          content: m.content,
          timestamp: m.timestamp,
          actions: m.actions,
          ok: m.ok ?? true,
          failureType: m.failure_type ?? null,
        }));
        setMessages(restored);
      } catch {
        // History is a convenience; ignore failures and start fresh.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [setMessages]);

  // Keyboard shortcut: Ctrl+/ to toggle
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key === "/") {
        e.preventDefault();
        setChatOpen(!chatOpen);
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [chatOpen, setChatOpen]);

  /**
   * Send a prompt to the assistant and render the response.
   * `addUser` controls whether a user bubble is added (false on retry, so the
   * failed prompt isn't duplicated).
   */
  const runAssistant = useCallback(
    async (content: string, addUser: boolean) => {
      if (addUser) addUserMessage(content);
      setTyping(true);

      const context: ChatContext = { page: location.pathname };

      try {
        const data = await sendChatMessage(content, context);
        setTyping(false);
        addAssistantMessage(uuid(), data.content || "No response", data.actions ?? [], {
          ok: data.ok,
          failureType: data.failure_type,
          retryable: data.retryable,
          degraded: data.degraded,
          provider: data.provider,
          prompt: content,
        });
      } catch {
        // Network/transport failure (backend unreachable, 5xx, etc.).
        // Be honest about it rather than fabricating a response.
        setTyping(false);
        addAssistantMessage(
          uuid(),
          "I couldn't reach the server. Please check your connection and try again.",
          [],
          { ok: false, failureType: "engine_error", retryable: true, prompt: content }
        );
      }
    },
    [addUserMessage, setTyping, addAssistantMessage, location.pathname]
  );

  const handleSend = useCallback((content: string) => runAssistant(content, true), [runAssistant]);

  const handleRetry = useCallback(
    (prompt: string) => runAssistant(prompt, false),
    [runAssistant]
  );

  const handleSuggestionClick = useCallback(
    (text: string) => {
      handleSend(text);
    },
    [handleSend]
  );

  if (!chatOpen) return null;

  return (
    <aside
      role="complementary"
      aria-label="MK Chat Assistant"
      className={cn(
        "w-96 shrink-0 border-l border-mk-border bg-mk-surface",
        "flex flex-col h-full",
        "animate-slide-in-right",
        // Mobile: full-screen overlay with safe areas
        "max-lg:fixed max-lg:inset-0 max-lg:w-full max-lg:z-[300] max-lg:border-l-0",
        "max-lg:pt-[env(safe-area-inset-top)] max-lg:pb-[env(safe-area-inset-bottom)]"
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-mk-border shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-full bg-mk-accent/20 flex items-center justify-center">
            <span className="text-mk-accent text-[10px] font-bold">MK</span>
          </div>
          <span className="text-sm font-semibold text-mk-text-primary">MK Chat</span>
        </div>
        <div className="flex items-center gap-0.5">
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => setChatOpen(false)}
            aria-label="Minimize chat"
            className="hidden lg:inline-flex"
          >
            <Minus size={14} />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => setChatOpen(false)}
            aria-label="Close chat"
          >
            <X size={14} />
          </Button>
        </div>
      </div>

      {/* Messages area */}
      <ScrollArea ref={scrollRef} className="flex-1 px-3 py-4">
        <div className="flex flex-col gap-4">
          {messages.length === 0 && (
            <div className="text-center py-8">
              <div className="w-12 h-12 rounded-full bg-mk-accent/10 border border-mk-accent/20 mx-auto mb-3 flex items-center justify-center">
                <span className="text-mk-accent font-bold text-lg">MK</span>
              </div>
              <p className="text-sm text-mk-text-secondary mb-1">
                Hi! I&apos;m monitoring your server.
              </p>
              <p className="text-xs text-mk-text-muted">
                Everything looks healthy. What can I help with?
              </p>
            </div>
          )}
          {messages.map((msg) => (
            <ChatBubble key={msg.id} message={msg} onRetry={handleRetry} />
          ))}
          {isTyping && <TypingIndicator />}
        </div>
      </ScrollArea>

      {/* Input */}
      <ChatInput onSend={handleSend} />

      {/* Context-aware suggestions */}
      <ContextSuggestions onSuggestionClick={handleSuggestionClick} />
    </aside>
  );
}
