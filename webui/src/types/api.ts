/**
 * MK OS API Types
 * ================
 * Shared response types used across all API endpoints.
 */

/** Standard paginated response wrapper */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
}

/** Auth login response */
export interface AuthResponse {
  token: string;
  expires: string;
}

/** Auth status check */
export interface AuthStatus {
  authenticated: boolean;
  expires: string;
}

/** Alert severity levels */
export type AlertSeverity = "critical" | "warning" | "info";

/** Dashboard alert */
export interface Alert {
  id: string;
  severity: AlertSeverity;
  message: string;
  timestamp: string;
  dismissed: boolean;
  source: string;
}

/** Activity log entry */
export interface ActivityEntry {
  id: string;
  timestamp: string;
  message: string;
  type: "backup" | "container" | "snapshot" | "login" | "system" | "update";
}

/** Dashboard summary metrics */
export interface DashboardSummary {
  cpu: {
    usage_percent: number;
    cores: number;
    model: string;
    temperature: number;
  };
  ram: {
    used_bytes: number;
    total_bytes: number;
    usage_percent: number;
  };
  network: {
    in_bytes_per_sec: number;
    out_bytes_per_sec: number;
    interface: string;
  };
  disk: {
    used_bytes: number;
    total_bytes: number;
    usage_percent: number;
  };
  health: {
    storage: "healthy" | "degraded" | "critical";
    network_interfaces: number;
    apps_running: number;
    apps_total: number;
    last_backup: string;
    temperature: number;
    temperature_status: "normal" | "warm" | "hot";
  };
}
