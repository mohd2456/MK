/**
 * ChatBubble Component
 * =====================
 * Renders a single chat message bubble.
 * User messages: right-aligned, darker blue background.
 * MK messages: left-aligned, deep navy background.
 * Supports inline action buttons and streaming indicator.
 *
 * When an assistant reply is an AI-failure fallback (`ok === false`) the
 * bubble is styled distinctly (warning border + icon, `role="alert"`) so the
 * failure is obvious and accessible, instead of masquerading as a normal
 * answer. A subtle badge marks replies produced in degraded (no-LLM) mode.
 */

import { AlertTriangle } from "lucide-react";
import type { ChatMessage, AIFailureType } from "@/types/chat";
import { cn } from "@/lib/utils";
import { formatRelativeTime } from "@/lib/utils";
import { ActionButton } from "./ActionButton";

interface ChatBubbleProps {
  message: ChatMessage;
}

/** Human-friendly, non-technical summary of an AI-failure type. */
function failureLabel(type: AIFailureType): string {
  switch (type) {
    case "timeout":
      return "The assistant took too long to respond.";
    case "engine_error":
      return "The assistant hit an unexpected error.";
    case "empty_output":
      return "The assistant didn't return a response.";
    case "malformed_output":
      return "The assistant's response looked unreliable.";
    case "schema_invalid":
      return "The assistant's structured response was invalid.";
    case "no_engine":
      return "No assistant engine is available.";
    case "provider_unavailable":
      return "No AI provider is currently reachable.";
    default:
      return "The assistant couldn't complete that request.";
  }
}

export function ChatBubble({ message }: ChatBubbleProps) {
  const isUser = message.role === "user";
  const isFailure = !isUser && message.ok === false;
  const isDegraded = !isUser && message.degraded === true;

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
        role={isFailure ? "alert" : undefined}
        className={cn(
          "max-w-[85%] rounded-[12px] px-3.5 py-2.5 text-sm leading-relaxed",
          "border",
          isFailure
            ? "bg-mk-error/10 border-mk-error/40 text-mk-text-primary"
            : isUser
              ? "bg-mk-chat-user border-mk-chat-border text-mk-text-primary"
              : "bg-mk-chat-mk border-mk-chat-border text-mk-text-primary"
        )}
      >
        {/* Failure banner */}
        {isFailure && (
          <div className="flex items-center gap-1.5 mb-1.5 text-[11px] font-medium text-mk-error">
            <AlertTriangle size={12} aria-hidden="true" />
            <span>{failureLabel(message.failureType ?? null)}</span>
          </div>
        )}

        {/* Degraded (no-LLM) badge */}
        {isDegraded && !isFailure && (
          <div className="mb-1.5">
            <span className="inline-block text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-mk-warning/15 text-mk-warning border border-mk-warning/30">
              Limited mode
            </span>
          </div>
        )}

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
