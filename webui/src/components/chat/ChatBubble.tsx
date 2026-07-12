/**
 * ChatBubble Component
 * =====================
 * Renders a single chat message bubble.
 * User messages: right-aligned, darker blue background.
 * MK messages: left-aligned, deep navy background.
 *
 * Assistant messages carry an AI-failure envelope: when `ok` is false the
 * bubble is styled as an error, shows a short failure label, and (when the
 * failure is retryable) offers a Retry button. A successful-but-`degraded`
 * reply shows a subtle "limited mode" note.
 */

import { AlertTriangle, RotateCw } from "lucide-react";
import type { AIFailureType, ChatMessage } from "@/types/chat";
import { cn } from "@/lib/utils";
import { formatRelativeTime } from "@/lib/utils";
import { ActionButton } from "./ActionButton";

interface ChatBubbleProps {
  message: ChatMessage;
  onRetry?: (prompt: string) => void;
}

/** Short, human-friendly labels for each failure type. */
const FAILURE_LABELS: Record<AIFailureType, string> = {
  timeout: "Timed out",
  engine_error: "Something went wrong",
  empty_output: "No response produced",
  malformed_output: "Response was garbled",
  schema_invalid: "Invalid result",
  no_engine: "AI not configured",
  provider_unavailable: "AI provider unavailable",
  invalid_input: "Invalid input",
};

export function ChatBubble({ message, onRetry }: ChatBubbleProps) {
  const isUser = message.role === "user";
  const isFailure = message.role === "assistant" && message.ok === false;
  const isDegraded = message.role === "assistant" && message.ok !== false && message.degraded;
  const canRetry = isFailure && message.retryable && !!message.prompt && !!onRetry;
  const failureLabel = message.failureType ? FAILURE_LABELS[message.failureType] : "Unavailable";

  return (
    <div
      className={cn("flex flex-col gap-1 animate-fade-in", isUser ? "items-end" : "items-start")}
    >
      {/* Sender label */}
      <span className="text-[10px] text-mk-text-muted font-medium px-1">
        {isUser ? "You" : "MK"}
      </span>

      {/* Bubble */}
      <div
        role={isFailure ? "alert" : undefined}
        className={cn(
          "max-w-[85%] rounded-[12px] px-3.5 py-2.5 text-sm leading-relaxed border",
          isUser && "bg-mk-chat-user border-mk-chat-border text-mk-text-primary",
          !isUser && !isFailure && "bg-mk-chat-mk border-mk-chat-border text-mk-text-primary",
          isFailure && "bg-mk-error/10 border-mk-error/40 text-mk-text-primary"
        )}
      >
        {/* Failure header */}
        {isFailure && (
          <div className="flex items-center gap-1.5 mb-1.5 text-mk-error">
            <AlertTriangle size={13} className="shrink-0" />
            <span className="text-[11px] font-semibold">{failureLabel}</span>
          </div>
        )}

        {/* Message content */}
        <div className="whitespace-pre-wrap break-words">{message.content}</div>

        {/* Degraded (successful but reduced-capability) note */}
        {isDegraded && (
          <div className="mt-1.5 text-[10px] text-mk-warning">
            Limited mode — no AI provider configured.
          </div>
        )}

        {/* Streaming cursor */}
        {message.streaming && (
          <span className="inline-block w-1.5 h-4 bg-mk-accent/70 animate-pulse-slow ml-0.5 align-middle rounded-sm" />
        )}

        {/* Retry affordance */}
        {canRetry && (
          <div className="mt-2.5 pt-2.5 border-t border-mk-error/20">
            <button
              type="button"
              onClick={() => onRetry!(message.prompt!)}
              className={cn(
                "inline-flex items-center gap-1.5 text-[11px] px-2 py-1 rounded-md",
                "bg-mk-elevated border border-mk-border text-mk-text-secondary",
                "hover:text-mk-accent hover:border-mk-accent/30",
                "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-mk-accent/50",
                "transition-all duration-[150ms]"
              )}
            >
              <RotateCw size={12} />
              Retry
            </button>
          </div>
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
