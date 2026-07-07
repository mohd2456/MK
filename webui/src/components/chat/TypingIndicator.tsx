/**
 * TypingIndicator Component
 * ==========================
 * Animated dots showing that MK is composing a response.
 */

export function TypingIndicator() {
  return (
    <div className="flex items-center gap-1.5 px-1">
      <span className="text-[10px] text-mk-text-muted font-medium">MK is typing</span>
      <div className="flex gap-0.5">
        <span className="w-1 h-1 rounded-full bg-mk-accent/70 animate-bounce [animation-delay:0ms]" />
        <span className="w-1 h-1 rounded-full bg-mk-accent/70 animate-bounce [animation-delay:150ms]" />
        <span className="w-1 h-1 rounded-full bg-mk-accent/70 animate-bounce [animation-delay:300ms]" />
      </div>
    </div>
  );
}
