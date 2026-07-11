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
import { Minus, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/stores/uiStore";
import { useChatStore } from "@/stores/chatStore";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChatBubble } from "@/components/chat/ChatBubble";
import { ChatInput } from "@/components/chat/ChatInput";
import { TypingIndicator } from "@/components/chat/TypingIndicator";
import { ContextSuggestions } from "@/components/chat/ContextSuggestions";

export function ChatPanel() {
  const { chatOpen, setChatOpen } = useUIStore();
  const { messages, isTyping, addUserMessage, setTyping, addAssistantMessage } = useChatStore();
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isTyping]);

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

  const handleSend = useCallback(
    async (content: string) => {
      const msgId = addUserMessage(content);
      setTyping(true);

      // Call real API endpoint
      try {
        const response = await fetch("/api/v1/chat/message", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ content, context: {} }),
        });
        const data = await response.json();
        setTyping(false);
        addAssistantMessage(
          crypto.randomUUID(),
          data.content || "No response",
          data.actions || []
        );
      } catch {
        // Fallback to simulated if backend unavailable
        setTimeout(() => {
          setTyping(false);
          addAssistantMessage(
            crypto.randomUUID(),
            getSimulatedResponse(content),
            getSimulatedActions(content)
          );
        }, 800);
      }

      void msgId;
    },
    [addUserMessage, setTyping, addAssistantMessage]
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
            <ChatBubble key={msg.id} message={msg} />
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

// ─── Simulated Responses (for demo without backend) ───

function getSimulatedResponse(input: string): string {
  const lower = input.toLowerCase();

  if (lower.includes("pool") || lower.includes("storage") || lower.includes("health")) {
    return "Your storage is looking great! The tank pool is at 75% capacity (36 TB / 48 TB) with RAIDZ2 protection. All disks are reporting SMART PASS. The fast pool (mirror) is at 40%. No scrub errors detected in the last run.";
  }
  if (lower.includes("backup")) {
    return "Last backup completed 2 hours ago (daily-media job). All 4 backup jobs are on schedule. The weekly-full to offsite ran successfully on Sunday. Want me to start a manual backup now?";
  }
  if (lower.includes("alert") || lower.includes("attention")) {
    return "You have 3 active alerts:\n\n1. Disk sda temperature hit 55C during the last scrub (resolved - now 38C)\n2. Tank pool is at 75% capacity - consider expanding\n3. A system update is available (linux-image 6.6.10)\n\nNothing critical right now.";
  }
  if (lower.includes("container") || lower.includes("ram") || lower.includes("docker")) {
    return "Top containers by RAM usage:\n1. plex - 2.1 GB (media transcoding)\n2. sonarr - 512 MB\n3. radarr - 480 MB\n\nAll 12 containers are running. Total container RAM: 4.2 GB of 64 GB available.";
  }
  if (lower.includes("temperature") || lower.includes("temp") || lower.includes("disk")) {
    return "Current disk temperatures:\n- sda: 38C (normal)\n- sdb: 40C (normal)\n- sdc: 42C (normal)\n- nvme0: 45C (normal)\n\nAll within safe operating range. sda peaked at 55C during Sunday's scrub, which is expected for extended I/O.";
  }
  if (lower.includes("system") || lower.includes("uptime") || lower.includes("doing")) {
    return "System is running smoothly! Uptime: 47 days. CPU at 12% average, RAM at 50% (32/64 GB). Network is stable on both interfaces. No failed services. You're in good shape.";
  }

  return "I'm here to help manage your server. I can check on storage health, container status, backups, network configuration, or anything else you need. Just ask!";
}

function getSimulatedActions(input: string) {
  const lower = input.toLowerCase();

  if (lower.includes("backup")) {
    return [
      { label: "Start backup now", action: "api_call" as const, method: "POST" as const, endpoint: "/api/v1/protection/jobs/1/run" },
      { label: "View backup history", action: "navigate" as const, target: "/protection" },
    ];
  }
  if (lower.includes("pool") || lower.includes("storage")) {
    return [
      { label: "View pool details", action: "navigate" as const, target: "/storage" },
      { label: "Create snapshot", action: "api_call" as const, method: "POST" as const, endpoint: "/api/v1/storage/snapshots" },
    ];
  }
  if (lower.includes("alert")) {
    return [
      { label: "Dismiss all", action: "api_call" as const, method: "POST" as const, endpoint: "/api/v1/dashboard/dismiss" },
      { label: "View system updates", action: "navigate" as const, target: "/system" },
    ];
  }
  return undefined;
}
