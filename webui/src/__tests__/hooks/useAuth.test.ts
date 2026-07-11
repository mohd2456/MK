/**
 * useAuth Hook Tests
 * ===================
 * Tests the auth hook's login, logout, and session checking behavior.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useAuth } from "@/hooks/useAuth";
import * as api from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";

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

describe("useAuth", () => {
  beforeEach(() => {
    // Reset auth store state before each test
    const store = useAuthStore.getState();
    store.logout();
    useAuthStore.setState({ loginAttempts: 0, lockoutUntil: null });
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("starts unauthenticated", () => {
    const { result } = renderHook(() => useAuth());
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("logs in successfully with valid PIN", async () => {
    vi.mocked(api.post).mockResolvedValueOnce({
      token: "test-token-123",
      expires: "2025-01-01T00:00:00Z",
    });

    const { result } = renderHook(() => useAuth());

    let loginResult: boolean | undefined;
    await act(async () => {
      loginResult = await result.current.login("1234");
    });

    expect(loginResult).toBe(true);
    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.error).toBeNull();
  });

  it("handles failed login with invalid PIN", async () => {
    const error = new api.ApiError(401, "Unauthorized");
    vi.mocked(api.post).mockRejectedValueOnce(error);

    const { result } = renderHook(() => useAuth());

    let loginResult: boolean | undefined;
    await act(async () => {
      loginResult = await result.current.login("0000");
    });

    expect(loginResult).toBe(false);
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.error).toBe("Invalid PIN");
  });

  it("logs out successfully", async () => {
    // First login
    vi.mocked(api.post).mockResolvedValueOnce({
      token: "test-token-123",
      expires: "2025-01-01T00:00:00Z",
    });

    const { result } = renderHook(() => useAuth());

    await act(async () => {
      await result.current.login("1234");
    });

    expect(result.current.isAuthenticated).toBe(true);

    // Then logout
    vi.mocked(api.post).mockResolvedValueOnce(undefined);

    await act(async () => {
      await result.current.logout();
    });

    expect(result.current.isAuthenticated).toBe(false);
  });

  it("checks session validity", async () => {
    // Setup: login first
    vi.mocked(api.post).mockResolvedValueOnce({
      token: "test-token-123",
      expires: "2025-01-01T00:00:00Z",
    });

    const { result } = renderHook(() => useAuth());

    await act(async () => {
      await result.current.login("1234");
    });

    // Check session - valid
    vi.mocked(api.get).mockResolvedValueOnce({ authenticated: true });

    let sessionValid: boolean | undefined;
    await act(async () => {
      sessionValid = await result.current.checkSession();
    });

    expect(sessionValid).toBe(true);
  });

  it("handles expired session check", async () => {
    // Setup: login first
    vi.mocked(api.post).mockResolvedValueOnce({
      token: "test-token-123",
      expires: "2025-01-01T00:00:00Z",
    });

    const { result } = renderHook(() => useAuth());

    await act(async () => {
      await result.current.login("1234");
    });

    // Check session - invalid
    vi.mocked(api.get).mockResolvedValueOnce({ authenticated: false });

    await act(async () => {
      await result.current.checkSession();
    });

    expect(result.current.isAuthenticated).toBe(false);
  });
});
