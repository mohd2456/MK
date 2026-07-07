/**
 * Authentication Store
 * =====================
 * Manages PIN login state, session token, and lockout logic.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";
import { MAX_LOGIN_ATTEMPTS, LOCKOUT_DURATION } from "@/lib/constants";

interface AuthState {
  isAuthenticated: boolean;
  token: string | null;
  tokenExpires: string | null;
  loginAttempts: number;
  lockoutUntil: number | null;

  // Actions
  login: (token: string, expires: string) => void;
  logout: () => void;
  recordFailedAttempt: () => void;
  isLockedOut: () => boolean;
  getRemainingLockoutSeconds: () => number;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      isAuthenticated: false,
      token: null,
      tokenExpires: null,
      loginAttempts: 0,
      lockoutUntil: null,

      login: (token, expires) =>
        set({
          isAuthenticated: true,
          token,
          tokenExpires: expires,
          loginAttempts: 0,
          lockoutUntil: null,
        }),

      logout: () =>
        set({
          isAuthenticated: false,
          token: null,
          tokenExpires: null,
        }),

      recordFailedAttempt: () => {
        const attempts = get().loginAttempts + 1;
        const lockoutUntil =
          attempts >= MAX_LOGIN_ATTEMPTS
            ? Date.now() + LOCKOUT_DURATION
            : null;
        set({ loginAttempts: attempts, lockoutUntil });
      },

      isLockedOut: () => {
        const { lockoutUntil } = get();
        if (!lockoutUntil) return false;
        if (Date.now() >= lockoutUntil) {
          // Lockout expired, reset
          set({ lockoutUntil: null, loginAttempts: 0 });
          return false;
        }
        return true;
      },

      getRemainingLockoutSeconds: () => {
        const { lockoutUntil } = get();
        if (!lockoutUntil) return 0;
        const remaining = Math.ceil((lockoutUntil - Date.now()) / 1000);
        return Math.max(0, remaining);
      },
    }),
    {
      name: "mk-auth",
      partialize: (state) => ({
        isAuthenticated: state.isAuthenticated,
        token: state.token,
        tokenExpires: state.tokenExpires,
      }),
    }
  )
);
