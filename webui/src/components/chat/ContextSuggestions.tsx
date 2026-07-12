/**
 * ContextSuggestions Component
 * =============================
 * Page-aware suggestion chips at the bottom of the chat panel.
 *
 * Suggestions are fetched from the backend (`GET /api/v1/chat/suggestions`)
 * based on the current route, so the "what can I do here?" logic lives in one
 * place (src/mk/wrapper/context.py) and stays in sync across surfaces. If the
 * backend is unavailable, we fall back to a built-in static set so the panel
 * is never empty.
 *
 * Activating a chip sends its `command` to the assistant.
 */

import { useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useChatSuggestions } from "@/hooks/useApi";
import type { SuggestedAction } from "@/types/chat";

interface ContextSuggestionsProps {
  onSuggestionClick: (text: string) => void;
}

/** Built-in fallback used only when the backend can't be reached. */
const FALLBACK_SUGGESTIONS: Record<string, string[]> = {
  "/": ["Show me pool health", "Start a backup now", "Any alerts I should know about?"],
  "/storage": ["Show disk temperatures", "Create a snapshot of tank", "How much space is left?"],
  "/apps": ["Which containers use the most RAM?", "Restart the plex container", "Show stopped containers"],
  "/network": ["Show active WireGuard peers", "Check reverse proxy status", "What's my external IP?"],
  "/protection": ["When was the last backup?", "Run a scrub on tank", "Any failed backup jobs?"],
  "/media": ["What's in the drive?", "Show recent rips", "How big is my library?"],
  "/system": ["What services are running?", "Any updates available?", "Show system uptime"],
};

function fallbackFor(pathname: string): string[] {
  // Segment-based match: "/apps/x" matches "/apps", but "/media-manager"
  // must not match "/media". Mirrors the backend (src/mk/wrapper/context.py).
  const key =
    Object.keys(FALLBACK_SUGGESTIONS).find((path) =>
      path === "/" ? pathname === "/" : pathname === path || pathname.startsWith(path + "/")
    ) ?? "/";
  return FALLBACK_SUGGESTIONS[key] ?? FALLBACK_SUGGESTIONS["/"];
}

function contextLabel(pathname: string): string {
  if (pathname === "/") return "Dashboard";
  const seg = pathname.split("/").filter(Boolean)[0] ?? "";
  return seg.charAt(0).toUpperCase() + seg.slice(1);
}

export function ContextSuggestions({ onSuggestionClick }: ContextSuggestionsProps) {
  const location = useLocation();
  const pathname = location.pathname;

  const { data, isLoading, error } = useChatSuggestions(pathname);

  // Prefer backend suggestions; fall back to a static set on error/empty.
  const backend: SuggestedAction[] = data?.suggestions ?? [];
  const useBackend = !error && backend.length > 0;

  const chips: Array<{ key: string; label: string; command: string }> = useBackend
    ? backend.map((a) => ({ key: a.id, label: a.label, command: a.command }))
    : fallbackFor(pathname).map((text) => ({ key: text, label: text, command: text }));

  return (
    <div className="px-3 py-2 border-t border-mk-border bg-mk-surface/50">
      <p className="text-[10px] text-mk-text-muted mb-1.5">
        Context: <span className="text-mk-text-secondary">{contextLabel(pathname)}</span>
      </p>

      {isLoading && backend.length === 0 && !error ? (
        <div className="flex flex-wrap gap-1" aria-hidden="true">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="h-6 w-24 rounded-full bg-mk-elevated border border-mk-border animate-pulse-slow"
            />
          ))}
        </div>
      ) : (
        <div
          className="flex flex-wrap gap-1"
          role="group"
          aria-label={`Suggestions for ${contextLabel(pathname)}`}
        >
          {chips.slice(0, 4).map((chip) => (
            <button
              key={chip.key}
              type="button"
              title={chip.command}
              onClick={() => onSuggestionClick(chip.command)}
              className={cn(
                "text-[11px] px-2 py-1 rounded-full",
                "bg-mk-elevated border border-mk-border",
                "text-mk-text-muted hover:text-mk-accent hover:border-mk-accent/30",
                "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-mk-accent/50",
                "transition-all duration-[150ms]",
                "truncate max-w-full"
              )}
            >
              {chip.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
