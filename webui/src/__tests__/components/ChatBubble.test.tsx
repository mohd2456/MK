/**
 * ChatBubble Tests
 * =================
 * Verifies success, AI-failure, degraded, and retry rendering.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@/test/utils";
import { ChatBubble } from "@/components/chat/ChatBubble";
import type { ChatMessage } from "@/types/chat";

function makeMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: "m1",
    role: "assistant",
    content: "All systems nominal.",
    timestamp: new Date().toISOString(),
    ...overrides,
  };
}

describe("ChatBubble", () => {
  it("renders a normal assistant message without failure styling", () => {
    render(<ChatBubble message={makeMessage()} />);
    expect(screen.getByText("All systems nominal.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders a user message", () => {
    render(<ChatBubble message={makeMessage({ role: "user", content: "hello" })} />);
    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(screen.getByText("You")).toBeInTheDocument();
  });

  it("renders an AI-failure message as an alert with a label", () => {
    const msg = makeMessage({
      ok: false,
      failureType: "timeout",
      content: "That took too long.",
    });
    render(<ChatBubble message={msg} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Timed out")).toBeInTheDocument();
    expect(screen.getByText("That took too long.")).toBeInTheDocument();
  });

  it("shows a Retry button for retryable failures and calls onRetry with the prompt", () => {
    const onRetry = vi.fn();
    const msg = makeMessage({
      ok: false,
      failureType: "engine_error",
      retryable: true,
      prompt: "status",
      content: "Something went wrong.",
    });
    render(<ChatBubble message={msg} onRetry={onRetry} />);
    const retry = screen.getByRole("button", { name: /retry/i });
    fireEvent.click(retry);
    expect(onRetry).toHaveBeenCalledWith("status");
  });

  it("does not show Retry for non-retryable failures", () => {
    const msg = makeMessage({
      ok: false,
      failureType: "no_engine",
      retryable: false,
      content: "AI not configured.",
    });
    render(<ChatBubble message={msg} onRetry={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
    expect(screen.getByText("AI not configured")).toBeInTheDocument();
  });

  it("shows a limited-mode note for degraded (but ok) replies", () => {
    const msg = makeMessage({ ok: true, degraded: true, content: "Here's a basic answer." });
    render(<ChatBubble message={msg} />);
    expect(screen.getByText(/limited mode/i)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
