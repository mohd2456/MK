/**
 * NotificationCenter Component
 * =============================
 * A dropdown bell icon in the TopBar that shows proactive alerts from the
 * ops manager (pushed over WebSocket). Displays unread count badge, and a
 * scrollable list of recent notifications with dismiss/clear actions.
 */

import { useState, useRef, useEffect } from "react";
import { Bell } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { useNotificationStore } from "@/stores/notificationStore";

function timeAgo(ts: number): string {
  const seconds = Math.floor((Date.now() / 1000 - ts));
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export function NotificationCenter() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { notifications, unreadCount, markAllRead, dismiss, clearAll } =
    useNotificationStore();

  // Close on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const toggle = () => {
    setOpen((v) => !v);
    if (!open && unreadCount > 0) markAllRead();
  };

  return (
    <div className="relative" ref={ref}>
      <Tooltip content="Notifications" side="bottom">
        <Button
          variant="ghost"
          size="icon"
          onClick={toggle}
          aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ""}`}
          className="relative"
        >
          <Bell size={18} className="text-mk-text-muted" />
          {unreadCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 text-[10px] font-bold bg-red-500 text-white rounded-full flex items-center justify-center">
              {unreadCount > 99 ? "99+" : unreadCount}
            </span>
          )}
        </Button>
      </Tooltip>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-80 max-h-96 bg-mk-surface border border-mk-border rounded-lg shadow-xl overflow-hidden z-[300]">
          <div className="flex items-center justify-between px-3 py-2 border-b border-mk-border">
            <span className="text-sm font-medium text-mk-text-primary">
              Notifications
            </span>
            {notifications.length > 0 && (
              <button
                onClick={clearAll}
                className="text-xs text-mk-text-muted hover:text-mk-accent"
              >
                Clear all
              </button>
            )}
          </div>
          <div className="overflow-y-auto max-h-80">
            {notifications.length === 0 ? (
              <div className="px-3 py-8 text-center text-sm text-mk-text-muted">
                No notifications yet
              </div>
            ) : (
              notifications.map((n) => (
                <div
                  key={n.id}
                  className="px-3 py-2 border-b border-mk-border/50 hover:bg-mk-elevated/50 group"
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm text-mk-text-primary leading-snug flex-1">
                      {n.message}
                    </p>
                    <button
                      onClick={() => dismiss(n.id)}
                      className="text-mk-text-muted hover:text-red-400 text-xs opacity-0 group-hover:opacity-100 transition-opacity"
                      aria-label="Dismiss"
                    >
                      ✕
                    </button>
                  </div>
                  <span className="text-xs text-mk-text-muted">
                    {timeAgo(n.timestamp)}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
