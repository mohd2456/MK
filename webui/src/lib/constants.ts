/**
 * MK OS Web UI Constants
 * ======================
 * Central configuration for API URLs, timeouts, and app-wide settings.
 */

/** Base URL for all API requests (proxied through Vite in dev) */
export const API_BASE = "/api/v1";

/** WebSocket URL for real-time chat and system events */
export const WS_URL =
  import.meta.env.VITE_WS_URL ||
  `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws/chat`;

/** How often to send WebSocket heartbeat pings (ms) */
export const WS_HEARTBEAT_INTERVAL = 30_000;

/** Max reconnection delay for WebSocket exponential backoff (ms) */
export const WS_MAX_RECONNECT_DELAY = 30_000;

/** SWR auto-refresh interval for dashboard metrics (ms) */
export const METRICS_REFRESH_INTERVAL = 5_000;

/** SWR auto-refresh interval for page data (ms) */
export const DATA_REFRESH_INTERVAL = 15_000;

/** Session token cookie name */
export const SESSION_COOKIE = "mk_session";

/** Session duration (7 days in ms) */
export const SESSION_DURATION = 7 * 24 * 60 * 60 * 1000;

/** Maximum login attempts before lockout */
export const MAX_LOGIN_ATTEMPTS = 10;

/** Lockout duration after max attempts (ms) */
export const LOCKOUT_DURATION = 5 * 60 * 1000;

/** Chat panel width in pixels */
export const CHAT_PANEL_WIDTH = 384;

/** Top navigation bar height in pixels */
export const TOP_BAR_HEIGHT = 56;

/** Animation durations */
export const ANIM = {
  fast: 150,
  normal: 250,
  slow: 350,
} as const;

/** Navigation items for the top bar */
export const NAV_ITEMS = [
  { label: "Dashboard", path: "/", icon: "LayoutDashboard" },
  { label: "Storage", path: "/storage", icon: "HardDrive" },
  { label: "Apps", path: "/apps", icon: "Container" },
  { label: "Network", path: "/network", icon: "Network" },
  { label: "Protection", path: "/protection", icon: "ShieldCheck" },
  { label: "Media", path: "/media", icon: "Disc3" },
  { label: "System", path: "/system", icon: "Settings" },
] as const;
