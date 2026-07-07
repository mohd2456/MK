/**
 * UI Preferences Store
 * =====================
 * Theme, chat panel visibility, and other UI state.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Theme = "dark" | "light";

interface UIState {
  theme: Theme;
  chatOpen: boolean;
  mobileNavOpen: boolean;

  // Actions
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
  toggleChat: () => void;
  setChatOpen: (open: boolean) => void;
  setMobileNavOpen: (open: boolean) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set, get) => ({
      theme: "dark",
      chatOpen: false,
      mobileNavOpen: false,

      setTheme: (theme) => {
        document.documentElement.classList.toggle("dark", theme === "dark");
        set({ theme });
      },

      toggleTheme: () => {
        const newTheme = get().theme === "dark" ? "light" : "dark";
        document.documentElement.classList.toggle("dark", newTheme === "dark");
        set({ theme: newTheme });
      },

      toggleChat: () => set((s) => ({ chatOpen: !s.chatOpen })),

      setChatOpen: (open) => set({ chatOpen: open }),

      setMobileNavOpen: (open) => set({ mobileNavOpen: open }),
    }),
    {
      name: "mk-ui",
      partialize: (state) => ({
        theme: state.theme,
        chatOpen: state.chatOpen,
      }),
    }
  )
);
