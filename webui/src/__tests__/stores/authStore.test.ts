/**
 * Auth Store Tests
 * =================
 * Tests for the Zustand authentication store: login, logout, lockout logic.
 */

import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { useAuthStore } from "@/stores/authStore";
import { MAX_LOGIN_ATTEMPTS, LOCKOUT_DURATION } from "@/lib/constants";

describe("authStore", () => {
  beforeEach(() => {
    // Reset the store before each test
    useAuthStore.setState({
      isAuthenticated: false,
      token: null,
      tokenExpires: null,
      loginAttempts: 0,
      lockoutUntil: null,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("starts in unauthenticated state", () => {
    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.token).toBeNull();
  });

  it("stores token on login", () => {
    const store = useAuthStore.getState();
    store.login("test-token-abc", "2025-12-31T23:59:59Z");

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
    expect(state.token).toBe("test-token-abc");
    expect(state.tokenExpires).toBe("2025-12-31T23:59:59Z");
    expect(state.loginAttempts).toBe(0);
  });

  it("clears token on logout", () => {
    const store = useAuthStore.getState();
    store.login("test-token-abc", "2025-12-31T23:59:59Z");
    store.logout();

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.token).toBeNull();
    expect(state.tokenExpires).toBeNull();
  });

  it("increments login attempts on failure", () => {
    const store = useAuthStore.getState();
    store.recordFailedAttempt();
    store.recordFailedAttempt();

    const state = useAuthStore.getState();
    expect(state.loginAttempts).toBe(2);
  });

  it("sets lockout after max attempts", () => {
    const store = useAuthStore.getState();

    for (let i = 0; i < MAX_LOGIN_ATTEMPTS; i++) {
      store.recordFailedAttempt();
    }

    const state = useAuthStore.getState();
    expect(state.lockoutUntil).not.toBeNull();
    expect(state.isLockedOut()).toBe(true);
  });

  it("reports not locked out when below max attempts", () => {
    const store = useAuthStore.getState();
    store.recordFailedAttempt();
    store.recordFailedAttempt();

    expect(store.isLockedOut()).toBe(false);
  });

  it("resets attempts on successful login", () => {
    const store = useAuthStore.getState();
    store.recordFailedAttempt();
    store.recordFailedAttempt();
    store.recordFailedAttempt();

    store.login("valid-token", "2025-12-31");

    const state = useAuthStore.getState();
    expect(state.loginAttempts).toBe(0);
    expect(state.lockoutUntil).toBeNull();
  });

  it("returns correct remaining lockout seconds", () => {
    vi.spyOn(Date, "now").mockReturnValue(1000000);

    const store = useAuthStore.getState();
    // Manually set lockout
    useAuthStore.setState({
      lockoutUntil: 1000000 + LOCKOUT_DURATION,
    });

    const seconds = store.getRemainingLockoutSeconds();
    expect(seconds).toBe(LOCKOUT_DURATION / 1000);
  });

  it("clears lockout when time has passed", () => {
    const store = useAuthStore.getState();

    // Set lockout in the past
    useAuthStore.setState({
      lockoutUntil: Date.now() - 1000,
      loginAttempts: MAX_LOGIN_ATTEMPTS,
    });

    // isLockedOut should clear expired lockout
    expect(store.isLockedOut()).toBe(false);

    const state = useAuthStore.getState();
    expect(state.loginAttempts).toBe(0);
    expect(state.lockoutUntil).toBeNull();
  });
});
