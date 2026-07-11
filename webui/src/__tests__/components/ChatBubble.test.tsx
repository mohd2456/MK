/**
 * ChatBubble Tests
 * =================
 * Focuses on graceful rendering of AI-failure and degraded replies so the
 * chat never "breaks" — a failed response is shown as a clearly-marked,
 * accessible alert instead of a normal-looking answer.
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@/test/utils";
import { ChatBubble } from "@/components/chat/ChatBubble";
import type { ChatMessage } from "@/types/chat";

function makeMessage(overrides: Partial<ChatMessage>): ChatMessage {
  return {
    id: "m1",
    role: "assistant",
    content: "Hello there",
    timestamp: new Date().toISOString(),
    ...overrides,
  };
}

describe("ChatBubble", () => {
  it("renders a normal assistant reply without an alert", () => {
    render(<ChatBubble message={makeMessage({ ok: true, content: "All good" })} />);
    expect(screen.getByText("All good")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders a failure reply as an accessible alert with a friendly label", () => {
    render(
      <ChatBubble
        message={makeMessage({
          ok: false,
          failureType: "timeout",
          content: "Sorry, I couldn't reach the assistant right now.",
        })}
      />
    );

    const alert = screen.getByRole("alert");
    expect(alert).toBeInTheDocument();
    // Friendly, non-technical failure summary is shown.
    expect(screen.getByText(/took too long to respond/i)).toBeInTheDocument();
    // The safe fallback content is still displayed.
    expect(screen.getByText(/couldn't reach the assistant/i)).toBeInTheDocument();
  });

  it("maps each failure type to a distinct friendly message", () => {
    const { rerender } = render(
      <ChatBubble message={makeMessage({ ok: false, failureType: "no_engine" })} />
    );
    expect(screen.getByText(/no assistant engine is available/i)).toBeInTheDocument();

    rerender(
      <ChatBubble message={makeMessage({ ok: false, failureType: "provider_unavailable" })} />
    );
    expect(screen.getByText(/no ai provider is currently reachable/i)).toBeInTheDocument();
  });

  it("shows a 'Limited mode' badge for degraded (no-LLM) replies", () => {
    render(
      <ChatBubble message={makeMessage({ ok: true, degraded: true, content: "Command-only reply" })} />
    );
    expect(screen.getByText(/limited mode/i)).toBeInTheDocument();
    // Degraded is not a hard failure, so no alert role.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("does not treat user messages as failures", () => {
    render(<ChatBubble message={makeMessage({ role: "user", ok: false, content: "hi" })} />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("hi")).toBeInTheDocument();
  });
});
