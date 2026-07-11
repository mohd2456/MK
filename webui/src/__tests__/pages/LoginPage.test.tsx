/**
 * LoginPage Tests
 * ================
 * Tests for the PIN-based login page UI rendering and interaction.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@/test/utils";
import { LoginPage } from "@/pages/LoginPage";
import { useAuthStore } from "@/stores/authStore";

// Mock react-router-dom useNavigate
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// Mock the API module
vi.mock("@/lib/api", () => ({
  post: vi.fn(),
  get: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number;
    statusText: string;
    constructor(status: number, statusText: string) {
      super(`API Error ${status}: ${statusText}`);
      this.name = "ApiError";
      this.status = status;
      this.statusText = statusText;
    }
  },
}));

describe("LoginPage", () => {
  beforeEach(() => {
    // Reset auth store
    useAuthStore.setState({
      isAuthenticated: false,
      token: null,
      tokenExpires: null,
      loginAttempts: 0,
      lockoutUntil: null,
    });
    mockNavigate.mockClear();
    vi.clearAllMocks();
  });

  it("renders the PIN pad with all digits", () => {
    render(<LoginPage />);

    // Check all digit buttons are present
    for (let i = 0; i <= 9; i++) {
      expect(screen.getByRole("button", { name: String(i) })).toBeInTheDocument();
    }
  });

  it("renders the MK OS logo and title", () => {
    render(<LoginPage />);

    expect(screen.getByText("MK")).toBeInTheDocument();
    expect(screen.getByText("MK OS")).toBeInTheDocument();
    expect(screen.getByText("Enter your PIN")).toBeInTheDocument();
  });

  it("renders the backspace button", () => {
    render(<LoginPage />);

    expect(screen.getByRole("button", { name: /backspace/i })).toBeInTheDocument();
  });

  it("renders PIN dot indicators", () => {
    render(<LoginPage />);

    // There should be 4 PIN dot indicators (default PIN_LENGTH = 4)
    const dots = document.querySelectorAll(".rounded-full.bg-mk-border, .rounded-full.bg-mk-accent");
    expect(dots.length).toBeGreaterThanOrEqual(4);
  });

  it("shows forgot PIN help text", () => {
    render(<LoginPage />);

    expect(
      screen.getByText(/forgot pin\? reset via cli on the server/i)
    ).toBeInTheDocument();
  });

  it("allows digit input via button click", () => {
    render(<LoginPage />);

    // Click digit 1
    fireEvent.click(screen.getByRole("button", { name: "1" }));

    // One dot should now be filled (has accent bg)
    const filledDots = document.querySelectorAll(".bg-mk-accent.scale-110");
    expect(filledDots.length).toBe(1);
  });

  it("handles keyboard number input", () => {
    render(<LoginPage />);

    fireEvent.keyDown(document, { key: "5" });

    const filledDots = document.querySelectorAll(".bg-mk-accent.scale-110");
    expect(filledDots.length).toBe(1);
  });
});
