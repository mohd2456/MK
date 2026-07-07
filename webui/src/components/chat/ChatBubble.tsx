/**
 * ChatBubble Component
 * =====================
 * Renders a single chat message bubble.
 * User messages: right-aligned, darker blue background.
 * MK messages: left-aligned, deep navy background.
 * Supports inline action buttons and streaming indicator.
 */

import type { ChatMessage } from "@/types/chat";
import { cn } from "@/lib/utils";
import { formatRelativeTime } from "@/lib/utils";
import { ActionButton } from "./ActionButton";

interface ChatBubbleProps {
  message: ChatMessage;
}

export function ChatBubble({ message }: ChatBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div
      className={cn(
        "flex flex-col gap-1 animate-fade-in",
        isUser ? "items-end" : "items-start"
      )}
    >
      {/* Sender label */}
      <span className="text-[10px] text-mk-text-muted font-medium px-1">
        {isUser ? "You" : "MK"}
      </span>

      {/* Bubble */}
      <div
        className={cn(
          "max-w-[85%] rounded-[12px] px-3.5 py-2.5 text-sm leading-relaxed",
          "border",
          isUser
            ? "bg-mk-chat-user border-mk-chat-border text-mk-text-primary"
            : "bg-mk-chat-mk border-mk-chat-border text-mk-text-primary"
        )}
      >
        {/* Message content */}
        <div className="whitespace-pre-wrap break-words">{message.content}</div>

        {/* Streaming cursor */}
        {message.streaming && (
          <span className="inline-block w-1.5 h-4 bg-mk-accent/70 animate-pulse-slow ml-0.5 align-middle rounded-sm" />
        )}

        {/* Action buttons */}
        {message.actions && message.actions.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-2.5 pt-2.5 border-t border-mk-chat-border">
            {message.actions.map((action, i) => (
              <ActionButton key={i} action={action} />
            ))}
          </div>
        )}
      </div>

      {/* Timestamp */}
      <span className="text-[10px] text-mk-text-muted px-1">
        {formatRelativeTime(message.timestamp)}
      </span>
    </div>
  );
}
