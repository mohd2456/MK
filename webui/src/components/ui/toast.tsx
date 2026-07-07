/**
 * Toast Notification System
 * ==========================
 * Lightweight toast notifications for success/error/info feedback.
 * Uses a global store so any component can trigger toasts.
 */

import { CheckCircle2, XCircle, Info, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { create } from "zustand";

type ToastType = "success" | "error" | "info";

interface Toast {
  id: string;
  type: ToastType;
  message: string;
  duration?: number;
}

interface ToastStore {
  toasts: Toast[];
  addToast: (type: ToastType, message: string, duration?: number) => void;
  removeToast: (id: string) => void;
}

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],
  addToast: (type, message, duration = 4000) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    set((s) => ({ toasts: [...s.toasts, { id, type, message, duration }] }));
    if (duration > 0) {
      setTimeout(() => {
        set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
      }, duration);
    }
  },
  removeToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

/** Shorthand helpers */
export const toast = {
  success: (msg: string) => useToastStore.getState().addToast("success", msg),
  error: (msg: string) => useToastStore.getState().addToast("error", msg),
  info: (msg: string) => useToastStore.getState().addToast("info", msg),
};

const icons = {
  success: CheckCircle2,
  error: XCircle,
  info: Info,
};

const colors = {
  success: "border-mk-success/30 bg-mk-success/5",
  error: "border-mk-error/30 bg-mk-error/5",
  info: "border-mk-info/30 bg-mk-info/5",
};

const iconColors = {
  success: "text-mk-success",
  error: "text-mk-error",
  info: "text-mk-info",
};

export function ToastContainer() {
  const { toasts, removeToast } = useToastStore();

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-[calc(env(safe-area-inset-bottom)+16px)] right-4 left-4 sm:left-auto sm:w-80 z-[500] flex flex-col gap-2">
      {toasts.map((t) => {
        const Icon = icons[t.type];
        return (
          <div
            key={t.id}
            className={cn(
              "flex items-start gap-3 p-3 rounded-[8px] border",
              "bg-mk-surface shadow-lg animate-slide-up",
              colors[t.type]
            )}
          >
            <Icon size={16} className={cn("shrink-0 mt-0.5", iconColors[t.type])} />
            <p className="text-sm text-mk-text-primary flex-1">{t.message}</p>
            <button
              onClick={() => removeToast(t.id)}
              className="text-mk-text-muted hover:text-mk-text-primary shrink-0"
            >
              <X size={14} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
