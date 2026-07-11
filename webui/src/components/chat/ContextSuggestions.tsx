/**
 * ContextSuggestions Component
 * =============================
 * Page-aware suggestion chips at the bottom of the chat panel.
 *
 * The suggestions are fetched from the backend `GET /api/v1/chat/suggestions`
 * endpoint (via {@link useSuggestions}), keyed on the current route. The
 * backend (`mk.wrapper.context`) is the single source of truth, so the chips
 * always reflect what the assistant can actually do on the current screen.
 *
 * Loading, empty, and error states are all handled gracefully so the chat
 * panel never breaks when the backend is slow or unavailable.
 */

import { useLocation } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import { useSuggestions } from "@/hooks/useApi";
import { LoadingState } from "@/components/LoadingState";
import { cn } from "@/lib/utils";

interface ContextSuggestionsProps {
  /** Called with the suggestion's prompt text when a chip is clicked. */
  onSuggestionClick: (text: string) => void;
  /** Max number of chips to display (defaults to 3 to fit the panel). */
  limit?: number;
}

export function ContextSuggestions({ onSuggestionClick, limit = 3 }: ContextSuggestionsProps) {
  const location = useLocation();
  // Request a few extra so `limit` slicing below still has options if the
  // backend returns fewer for some routes.
  const { data, error, isLoading } = useSuggestions(location.pathname, Math.max(limit, 4));

  const contextLabel = data?.context_label ?? "Assistant";
  const suggestions = data?.suggestions ?? [];

  // Error: surface a quiet, non-blocking message rather than breaking the UI.
  if (error) {
    return (
      <div
        className="px-3 py-2 border-t border-mk-border bg-mk-surface/50"
        role="status"
      >
        <p className="flex items-center gap-1.5 text-[10px] text-mk-text-muted">
          <AlertTriangle size={11} className="text-mk-warning" aria-hidden="true" />
          Suggestions unavailable right now.
        </p>
      </div>
    );
  }

  // Loading: compact inline skeleton, keeps the panel height stable.
  if (isLoading) {
    return (
      <div className="px-3 py-2 border-t border-mk-border bg-mk-surface/50">
        <p className="text-[10px] text-mk-text-muted mb-1.5">Loading suggestions…</p>
        <LoadingState variant="inline" className="p-0" />
      </div>
    );
  }

  // Empty: nothing to suggest for this page — render nothing so the panel
  // stays clean instead of showing an empty container.
  if (suggestions.length === 0) {
    return null;
  }

  return (
    <nav
      aria-label={`Suggested actions for ${contextLabel}`}
      className="px-3 py-2 border-t border-mk-border bg-mk-surface/50"
    >
      <p className="text-[10px] text-mk-text-muted mb-1.5">
        Context: <span className="text-mk-text-secondary">{contextLabel}</span>
      </p>
      <div className="flex flex-wrap gap-1">
        {suggestions.slice(0, limit).map((suggestion) => (
          <button
            key={suggestion.id}
            type="button"
            onClick={() => onSuggestionClick(suggestion.prompt)}
            title={suggestion.prompt}
            aria-label={`Ask: ${suggestion.prompt}`}
            className={cn(
              "text-[11px] px-2 py-1 rounded-full",
              "bg-mk-elevated border border-mk-border",
              "text-mk-text-muted hover:text-mk-accent hover:border-mk-accent/30",
              "focus:outline-none focus-visible:ring-1 focus-visible:ring-mk-accent",
              "transition-all duration-[150ms]",
              "truncate max-w-full"
            )}
          >
            {suggestion.label}
          </button>
        ))}
      </div>
    </nav>
  );
}
