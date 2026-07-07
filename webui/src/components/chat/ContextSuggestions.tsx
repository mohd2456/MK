/**
 * ContextSuggestions Component
 * =============================
 * Page-aware suggestion chips at the bottom of the chat panel.
 * Changes based on which page the user is viewing.
 */

import { useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";

interface ContextSuggestionsProps {
  onSuggestionClick: (text: string) => void;
}

const suggestions: Record<string, string[]> = {
  "/": [
    "Show me pool health",
    "Start a backup now",
    "Any alerts I should know about?",
    "How's my system doing?",
  ],
  "/storage": [
    "Show disk temperatures",
    "Create a snapshot of tank",
    "Which disks need attention?",
    "How much space is left?",
  ],
  "/apps": [
    "Which containers are using the most RAM?",
    "Restart the plex container",
    "Show me stopped containers",
    "Deploy a new stack",
  ],
  "/network": [
    "Show active WireGuard peers",
    "Any firewall blocks today?",
    "Check reverse proxy status",
    "What's my external IP?",
  ],
  "/protection": [
    "When was the last backup?",
    "Run a scrub on tank",
    "Show replication lag",
    "Any failed backup jobs?",
  ],
  "/media": [
    "What's in the drive?",
    "Show recent rips",
    "How big is my library?",
    "Start ripping the disc",
  ],
  "/system": [
    "What services are running?",
    "Any updates available?",
    "Show system uptime",
    "Check UPS status",
  ],
};

export function ContextSuggestions({ onSuggestionClick }: ContextSuggestionsProps) {
  const location = useLocation();

  // Match the current page to get relevant suggestions
  const pagePath = Object.keys(suggestions).find((path) => {
    if (path === "/") return location.pathname === "/";
    return location.pathname.startsWith(path);
  }) ?? "/";

  const pageSuggestions = suggestions[pagePath] ?? suggestions["/"];
  const contextLabel = pagePath === "/" ? "Dashboard" : pagePath.slice(1).charAt(0).toUpperCase() + pagePath.slice(2);

  return (
    <div className="px-3 py-2 border-t border-mk-border bg-mk-surface/50">
      <p className="text-[10px] text-mk-text-muted mb-1.5">
        Context: <span className="text-mk-text-secondary">{contextLabel}</span>
      </p>
      <div className="flex flex-wrap gap-1">
        {pageSuggestions.slice(0, 3).map((suggestion) => (
          <button
            key={suggestion}
            onClick={() => onSuggestionClick(suggestion)}
            className={cn(
              "text-[11px] px-2 py-1 rounded-full",
              "bg-mk-elevated border border-mk-border",
              "text-mk-text-muted hover:text-mk-accent hover:border-mk-accent/30",
              "transition-all duration-[150ms]",
              "truncate max-w-full"
            )}
          >
            &ldquo;{suggestion}&rdquo;
          </button>
        ))}
      </div>
    </div>
  );
}
