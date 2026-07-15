/**
 * Notification Store
 * ===================
 * Manages the notification center: stores notifications pushed over the
 * WebSocket (from proactive ops alerts) and provides read/dismiss actions.
 */

import { create } from "zustand";

export interface Notification {
  id: string;
  message: string;
  timestamp: number;
  read: boolean;
}

interface NotificationState {
  notifications: Notification[];
  unreadCount: number;
  /** Add a new notification (from WS notification frame). */
  addNotification: (message: string, timestamp: number) => void;
  /** Mark all as read. */
  markAllRead: () => void;
  /** Dismiss (remove) a notification by id. */
  dismiss: (id: string) => void;
  /** Clear all notifications. */
  clearAll: () => void;
}

let _counter = 0;

export const useNotificationStore = create<NotificationState>((set) => ({
  notifications: [],
  unreadCount: 0,

  addNotification: (message, timestamp) => {
    _counter += 1;
    const n: Notification = {
      id: `notif-${_counter}`,
      message,
      timestamp,
      read: false,
    };
    set((s) => ({
      notifications: [n, ...s.notifications].slice(0, 100),
      unreadCount: s.unreadCount + 1,
    }));
  },

  markAllRead: () =>
    set((s) => ({
      notifications: s.notifications.map((n) => ({ ...n, read: true })),
      unreadCount: 0,
    })),

  dismiss: (id) =>
    set((s) => {
      const n = s.notifications.find((x) => x.id === id);
      const wasUnread = n && !n.read ? 1 : 0;
      return {
        notifications: s.notifications.filter((x) => x.id !== id),
        unreadCount: Math.max(0, s.unreadCount - wasUnread),
      };
    }),

  clearAll: () => set({ notifications: [], unreadCount: 0 }),
}));
