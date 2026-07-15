/**
 * Dashboard Stats Store
 * =====================
 * Zustand store for live system stats pushed over the WebSocket.
 * When a `stats_update` frame arrives, the store is updated and any
 * subscribed component re-renders with fresh numbers — no polling needed.
 *
 * Falls back to the HTTP GET /api/v1/dashboard/summary on initial load;
 * subsequent updates come in real-time via WS.
 */

import { create } from "zustand";

export interface DashboardStats {
  cpu_percent: number;
  ram_used_gb: number;
  ram_total_gb: number;
  ram_percent: number;
  disk_used_tb: number;
  disk_total_tb: number;
  disk_percent: number;
  containers_running: number;
  containers_total: number;
  timestamp: number;
}

interface DashboardState {
  stats: DashboardStats | null;
  lastUpdated: number | null;
  /** Apply a stats_update frame from the WebSocket. */
  applyStatsUpdate: (update: DashboardStats) => void;
  /** Apply the initial HTTP fetch result. */
  setInitialStats: (stats: DashboardStats) => void;
}

export const useDashboardStore = create<DashboardState>((set) => ({
  stats: null,
  lastUpdated: null,
  applyStatsUpdate: (update) =>
    set({ stats: update, lastUpdated: Date.now() }),
  setInitialStats: (stats) =>
    set({ stats, lastUpdated: Date.now() }),
}));
