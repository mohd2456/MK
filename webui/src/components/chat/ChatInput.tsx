/**
 * ChatInput Component
 * ====================
 * Message input area with send button.
 * Supports Enter to send, Shift+Enter for newline.
 */

import { useState, useRef, useCallback, type KeyboardEvent } from "react";
import { Send } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [value, onSend, disabled]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Auto-resize textarea
  const handleInput = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 120) + "px";
  };

  return (
    <div className="flex items-end gap-2 p-3 border-t border-mk-border bg-mk-surface">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => {
          setValue(e.target.value);
          handleInput();
        }}
        onKeyDown={handleKeyDown}
        placeholder="Type a message..."
        disabled={disabled}
        rows={1}
        className={cn(
          "flex-1 resize-none bg-mk-elevated rounded-[8px]",
          "px-3 py-2 text-sm text-mk-text-primary",
          "placeholder:text-mk-text-muted",
          "border border-mk-border",
          "focus:outline-none focus:ring-1 focus:ring-mk-accent focus:border-mk-accent",
          "disabled:opacity-50",
          "transition-all duration-[150ms]",
          "max-h-[120px]"
        )}
      />
      <Button
        size="icon"
        onClick={handleSend}
        disabled={!value.trim() || disabled}
        className="shrink-0"
        aria-label="Send message"
      >
        <Send size={16} />
      </Button>
    </div>
  );
}
