/**
 * ContextSuggestions Tests
 * =========================
 * Verifies the suggestion chips are wired to the real
 * `GET /api/v1/chat/suggestions` endpoint (via the `useSuggestions` hook) and
 * that loading, empty, error, and populated states all render correctly and
 * that clicking a chip sends the suggestion's *prompt* (not its label).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@/test/utils";
import { ContextSuggestions } from "@/components/chat/ContextSuggestions";
import type { SuggestionsResponse } from "@/types/chat";

// Mock the data hook so we control loading/error/data without real network.
const useSuggestionsMock = vi.fn();
vi.mock("@/hooks/useApi", () => ({
  useSuggestions: (path: string, limit?: number) => useSuggestionsMock(path, limit),
}));

type HookReturn = {
  data?: SuggestionsResponse;
  error?: unknown;
  isLoading: boolean;
};

function setHook(value: HookReturn) {
  useSuggestionsMock.mockReturnValue(value);
}

const sampleData: SuggestionsResponse = {
  path: "/",
  context_label: "Dashboard",
  suggestions: [
    { id: "pool-health", label: "Pool health", prompt: "Show me pool health", kind: "suggestion" },
    { id: "start-backup", label: "Start a backup", prompt: "Start a backup now", kind: "suggestion" },
    { id: "alerts", label: "Any alerts?", prompt: "Any alerts I should know about?", kind: "suggestion" },
    { id: "system-status", label: "System status", prompt: "How's my system doing?", kind: "suggestion" },
  ],
};

describe("ContextSuggestions", () => {
  beforeEach(() => {
    useSuggestionsMock.mockReset();
  });

  it("renders suggestion chips from the endpoint using labels", () => {
    setHook({ data: sampleData, isLoading: false });
    render(<ContextSuggestions onSuggestionClick={() => {}} />);

    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Pool health")).toBeInTheDocument();
    expect(screen.getByText("Start a backup")).toBeInTheDocument();
  });

  it("respects the limit prop (defaults to 3 chips)", () => {
    setHook({ data: sampleData, isLoading: false });
    render(<ContextSuggestions onSuggestionClick={() => {}} />);

    // Default limit is 3, so the 4th suggestion should not render.
    expect(screen.queryByText("System status")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(3);
  });

  it("sends the prompt (not the label) when a chip is clicked", () => {
    const onClick = vi.fn();
    setHook({ data: sampleData, isLoading: false });
    render(<ContextSuggestions onSuggestionClick={onClick} />);

    fireEvent.click(screen.getByText("Pool health"));
    expect(onClick).toHaveBeenCalledWith("Show me pool health");
  });

  it("shows a loading state while fetching", () => {
    setHook({ isLoading: true });
    render(<ContextSuggestions onSuggestionClick={() => {}} />);
    expect(screen.getByText(/loading suggestions/i)).toBeInTheDocument();
  });

  it("shows a graceful message on error", () => {
    setHook({ error: new Error("boom"), isLoading: false });
    render(<ContextSuggestions onSuggestionClick={() => {}} />);
    expect(screen.getByText(/suggestions unavailable/i)).toBeInTheDocument();
  });

  it("renders nothing when there are no suggestions", () => {
    setHook({
      data: { path: "/", context_label: "Dashboard", suggestions: [] },
      isLoading: false,
    });
    const { container } = render(<ContextSuggestions onSuggestionClick={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("exposes an accessible navigation landmark labelled by context", () => {
    setHook({ data: sampleData, isLoading: false });
    render(<ContextSuggestions onSuggestionClick={() => {}} />);
    expect(
      screen.getByRole("navigation", { name: /suggested actions for dashboard/i })
    ).toBeInTheDocument();
  });
});
