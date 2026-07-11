/**
 * ContextSuggestions Tests
 * =========================
 * Verifies backend-driven suggestions render and activate, and that the
 * component falls back to a static set when the backend errors.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@/test/utils";
import { ContextSuggestions } from "@/components/chat/ContextSuggestions";
import type { SuggestionsResponse } from "@/types/chat";

// Mock the SWR hook so we control loading / data / error states.
const mockHook = vi.fn();
vi.mock("@/hooks/useApi", () => ({
  useChatSuggestions: (page: string, selection?: string) => mockHook(page, selection),
}));

function makeResponse(): SuggestionsResponse {
  return {
    page: "/dashboard",
    suggestions: [
      {
        id: "dash.status",
        label: "System status",
        description: "Show a quick health overview",
        command: "status",
        category: "system",
        icon: "activity",
      },
      {
        id: "dash.alerts",
        label: "Active alerts",
        description: "List any current alerts",
        command: "show active alerts",
        category: "system",
        icon: "bell",
      },
    ],
  };
}

describe("ContextSuggestions", () => {
  beforeEach(() => {
    mockHook.mockReset();
  });

  it("renders backend suggestions and activates with the command", () => {
    mockHook.mockReturnValue({ data: makeResponse(), isLoading: false, error: undefined });
    const onClick = vi.fn();
    render(<ContextSuggestions onSuggestionClick={onClick} />);

    const btn = screen.getByRole("button", { name: "System status" });
    expect(btn).toBeInTheDocument();
    fireEvent.click(btn);
    // Activating sends the backend `command`, not the label.
    expect(onClick).toHaveBeenCalledWith("status");
  });

  it("falls back to static suggestions on backend error", () => {
    mockHook.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("network"),
    });
    const onClick = vi.fn();
    render(<ContextSuggestions onSuggestionClick={onClick} />);

    // At least one fallback chip is shown, and it is clickable.
    const items = screen.getAllByRole("button");
    expect(items.length).toBeGreaterThan(0);
    fireEvent.click(items[0]);
    expect(onClick).toHaveBeenCalled();
  });

  it("shows a loading skeleton while fetching with no data", () => {
    mockHook.mockReturnValue({ data: undefined, isLoading: true, error: undefined });
    const { container } = render(<ContextSuggestions onSuggestionClick={vi.fn()} />);
    // Skeleton chips are aria-hidden and render no buttons.
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(container.querySelector(".animate-pulse-slow")).toBeInTheDocument();
  });
});
