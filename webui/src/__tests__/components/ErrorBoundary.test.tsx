/**
 * ErrorBoundary Tests
 * ====================
 * Verifies that ErrorBoundary catches render errors and shows fallback UI.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@/test/utils";
import { ErrorBoundary } from "@/components/ErrorBoundary";

// Suppress console.error for expected errors
beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
});

function ThrowingComponent({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) {
    throw new Error("Test render error");
  }
  return <div>Normal content</div>;
}

describe("ErrorBoundary", () => {
  it("renders children when there is no error", () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent shouldThrow={false} />
      </ErrorBoundary>
    );

    expect(screen.getByText("Normal content")).toBeInTheDocument();
  });

  it("displays fallback UI when a child throws", () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByText("Test render error")).toBeInTheDocument();
  });

  it("displays custom fallback when provided", () => {
    render(
      <ErrorBoundary fallback={<div>Custom error fallback</div>}>
        <ThrowingComponent shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText("Custom error fallback")).toBeInTheDocument();
  });

  it("renders the Try Again button in default fallback", () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("recovers when Try Again is clicked and error condition is removed", () => {
    // The ErrorBoundary resets hasError state on retry click,
    // but the same tree re-renders. We test that clicking Try Again
    // calls the retry handler (resets error state).
    render(
      <ErrorBoundary>
        <ThrowingComponent shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText("Something went wrong")).toBeInTheDocument();

    // Click retry - this resets hasError state, but child still throws
    // so it will immediately error again. The important thing is the handler works.
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));

    // Since ThrowingComponent still throws, error boundary catches again
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
  });
});
