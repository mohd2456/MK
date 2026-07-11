/**
 * useAuth Hook
 * ==============
 * Wraps authStore and provides login/logout/checkSession functions
 * that call the actual API endpoints.
 */

import { useCallback, useState } from "react";
import { useAuthStore } from "@/stores/authStore";
import { post, get } from "@/lib/api";
import type { ApiError } from "@/lib/api";

interface LoginResponse {
  token: string;
  expires: string;
}

interface AuthStatusResponse {
  authenticated: boolean;
  expires?: string;
}

interface UseAuthReturn {
  /** Whether the user is authenticated */
  isAuthenticated: boolean;
  /** Whether an auth operation is in progress */
  isLoading: boolean;
  /** Error message from the last failed operation */
  error: string | null;
  /** Whether the user is locked out */
  isLockedOut: boolean;
  /** Remaining lockout seconds */
  lockoutSeconds: number;
  /** Attempt login with PIN */
  login: (pin: string) => Promise<boolean>;
  /** Log out the current session */
  logout: () => Promise<void>;
  /** Check if the current session is still valid */
  checkSession: () => Promise<boolean>;
}

export function useAuth(): UseAuthReturn {
  const store = useAuthStore();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const login = useCallback(async (pin: string): Promise<boolean> => {
    if (store.isLockedOut()) {
      setError("Too many failed attempts. Please wait.");
      return false;
    }

    setIsLoading(true);
    setError(null);

    try {
      const response = await post<LoginResponse>("/auth/login", { pin });
      store.login(response.token, response.expires);
      setIsLoading(false);
      return true;
    } catch (err) {
      const apiErr = err as ApiError;
      store.recordFailedAttempt();
      setError(apiErr.status === 401 ? "Invalid PIN" : "Login failed. Please try again.");
      setIsLoading(false);
      return false;
    }
  }, [store]);

  const logout = useCallback(async (): Promise<void> => {
    setIsLoading(true);
    try {
      await post("/auth/logout");
    } catch {
      // Logout should succeed locally even if API fails
    } finally {
      store.logout();
      setIsLoading(false);
      setError(null);
    }
  }, [store]);

  const checkSession = useCallback(async (): Promise<boolean> => {
    try {
      const response = await get<AuthStatusResponse>("/auth/status");
      if (!response.authenticated) {
        store.logout();
        return false;
      }
      return true;
    } catch {
      store.logout();
      return false;
    }
  }, [store]);

  return {
    isAuthenticated: store.isAuthenticated,
    isLoading,
    error,
    isLockedOut: store.isLockedOut(),
    lockoutSeconds: store.getRemainingLockoutSeconds(),
    login,
    logout,
    checkSession,
  };
}
