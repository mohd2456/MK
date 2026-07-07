/**
 * API Data Fetching Hooks
 * ========================
 * SWR-based hooks that fetch real data from the MK backend API.
 * Replaces all hardcoded mock data throughout the webui.
 */

import useSWR from "swr";
import { fetcher, post } from "@/lib/api";
import { METRICS_REFRESH_INTERVAL, DATA_REFRESH_INTERVAL } from "@/lib/constants";

// ─── Dashboard ───────────────────────────────────────────────────────

export interface DashboardSummaryResponse {
  cpu_percent: number;
  ram_used_gb: number;
  ram_total_gb: number;
  ram_percent: number;
  disk_used_tb: number;
  disk_total_tb: number;
  disk_percent: number;
  network_in_mbps: number;
  network_out_mbps: number;
  uptime_seconds: number;
  containers_running: number;
  containers_total: number;
  tailscale_connected: boolean;
  tailscale_ip: string;
}

export function useDashboardSummary() {
  return useSWR<DashboardSummaryResponse>(
    "/dashboard/summary",
    fetcher,
    { refreshInterval: METRICS_REFRESH_INTERVAL }
  );
}

// ─── Alerts ──────────────────────────────────────────────────────────

export interface AlertResponse {
  id: string;
  severity: string;
  message: string;
  check: string;
  fired_at: string;
}

export function useDashboardAlerts() {
  return useSWR<AlertResponse[]>(
    "/dashboard/alerts",
    fetcher,
    { refreshInterval: DATA_REFRESH_INTERVAL }
  );
}

// ─── Activity ────────────────────────────────────────────────────────

export interface ActivityResponse {
  events: Array<{
    id: string;
    timestamp: string;
    message: string;
    type: string;
  }>;
}

export function useDashboardActivity() {
  return useSWR<ActivityResponse>(
    "/dashboard/activity",
    fetcher,
    { refreshInterval: DATA_REFRESH_INTERVAL }
  );
}

// ─── System Info ─────────────────────────────────────────────────────

export interface SystemInfoResponse {
  hostname: string;
  os: string;
  kernel: string;
  arch: string;
  python: string;
  cpu_count: number;
  cpu_model: string;
  ram_total_gb: number;
  ram_used_gb: number;
  uptime_seconds: number;
}

export function useSystemInfo() {
  return useSWR<SystemInfoResponse>(
    "/system/info",
    fetcher,
    { refreshInterval: DATA_REFRESH_INTERVAL }
  );
}

// ─── System Health ───────────────────────────────────────────────────

export interface HealthCheckResult {
  name: string;
  severity: string;
  message: string;
  recommendations: string[];
}

export interface SystemHealthResponse {
  checks: HealthCheckResult[];
}

export function useSystemHealth() {
  return useSWR<SystemHealthResponse>(
    "/system/health",
    fetcher,
    { refreshInterval: DATA_REFRESH_INTERVAL }
  );
}

// ─── Containers ──────────────────────────────────────────────────────

export interface ContainerInfo {
  name: string;
  image: string;
  status: string;
  state: string;
  ports: string;
}

export interface ContainersResponse {
  containers: ContainerInfo[];
}

export function useContainers() {
  return useSWR<ContainersResponse>(
    "/apps/containers",
    fetcher,
    { refreshInterval: DATA_REFRESH_INTERVAL }
  );
}

// ─── Container Actions ───────────────────────────────────────────────

export async function restartContainer(name: string) {
  return post<{ status: string; container: string }>(
    `/apps/containers/${encodeURIComponent(name)}/restart`
  );
}

export async function stopContainer(name: string) {
  return post<{ status: string; container: string }>(
    `/apps/containers/${encodeURIComponent(name)}/stop`
  );
}

export async function startContainer(name: string) {
  return post<{ status: string; container: string }>(
    `/apps/containers/${encodeURIComponent(name)}/start`
  );
}

// ─── Network ─────────────────────────────────────────────────────────

export function useNetworkInterfaces() {
  return useSWR("/network/interfaces", fetcher, {
    refreshInterval: DATA_REFRESH_INTERVAL,
  });
}

export function useTailscaleStatus() {
  return useSWR("/network/tailscale", fetcher, {
    refreshInterval: DATA_REFRESH_INTERVAL,
  });
}

// ─── Services ────────────────────────────────────────────────────────

export interface ServicesResponse {
  services: string;
}

export function useSystemServices() {
  return useSWR<ServicesResponse>(
    "/system/services",
    fetcher,
    { refreshInterval: DATA_REFRESH_INTERVAL }
  );
}



// ─── V2: Storage (real data) ─────────────────────────────────

const fetcherV2 = <T>(endpoint: string): Promise<T> => {
  const url = `/api/v2${endpoint}`;
  return fetch(url, { credentials: "include" }).then((r) => {
    if (!r.ok) throw new Error(`API Error ${r.status}`);
    return r.json();
  });
};

export function useStoragePools() {
  return useSWR("v2-storage-pools", () => fetcherV2("/storage/pools"), {
    refreshInterval: DATA_REFRESH_INTERVAL,
  });
}

export function useStorageDatasets() {
  return useSWR("v2-storage-datasets", () => fetcherV2("/storage/datasets"), {
    refreshInterval: DATA_REFRESH_INTERVAL,
  });
}

export function useStorageDisks() {
  return useSWR("v2-storage-disks", () => fetcherV2("/storage/disks"), {
    refreshInterval: DATA_REFRESH_INTERVAL,
  });
}

export function useStorageSnapshots() {
  return useSWR("v2-storage-snapshots", () => fetcherV2("/storage/snapshots"), {
    refreshInterval: DATA_REFRESH_INTERVAL,
  });
}

// ─── V2: Network ─────────────────────────────────────────────

export function useNetworkInterfacesV2() {
  return useSWR("v2-network-interfaces", () => fetcherV2("/network/interfaces"), {
    refreshInterval: DATA_REFRESH_INTERVAL,
  });
}

// ─── V2: Media Manager ───────────────────────────────────────

export function useDropFolders() {
  return useSWR("v2-drop-folders", () => fetcherV2("/media-manager/folders"), {
    refreshInterval: DATA_REFRESH_INTERVAL,
  });
}

export function useProcessingQueue() {
  return useSWR("v2-processing-queue", () => fetcherV2("/media-manager/queue"), {
    refreshInterval: METRICS_REFRESH_INTERVAL,
  });
}

export function useDropStats() {
  return useSWR("v2-drop-stats", () => fetcherV2("/media-manager/stats"), {
    refreshInterval: DATA_REFRESH_INTERVAL,
  });
}

export function useDropHistory() {
  return useSWR("v2-drop-history", () => fetcherV2("/media-manager/history"), {
    refreshInterval: DATA_REFRESH_INTERVAL,
  });
}

// ─── V2: Protection ──────────────────────────────────────────

export function useBackupJobs() {
  return useSWR("v2-backup-jobs", () => fetcherV2("/protection/jobs"), {
    refreshInterval: DATA_REFRESH_INTERVAL,
  });
}

export function useProtectionSnapshots() {
  return useSWR("v2-protection-snapshots", () => fetcherV2("/protection/snapshots"), {
    refreshInterval: DATA_REFRESH_INTERVAL,
  });
}

// ─── V2: Docker Stacks ───────────────────────────────────────

export function useDockerStacks() {
  return useSWR("v2-stacks", () => fetcherV2("/stacks"), {
    refreshInterval: DATA_REFRESH_INTERVAL,
  });
}

// ─── V2: System Updates ──────────────────────────────────────

export function useSystemUpdates() {
  return useSWR("v2-system-updates", () => fetcherV2("/system/updates"), {
    refreshInterval: 60_000,
  });
}

// ─── V2: Media/Disc ──────────────────────────────────────────

export function useDiscStatus() {
  return useSWR("v2-disc-status", () => fetcherV2("/media/disc"), {
    refreshInterval: DATA_REFRESH_INTERVAL,
  });
}

export function useMediaLibrary() {
  return useSWR("v2-media-library", () => fetcherV2("/media/library"), {
    refreshInterval: DATA_REFRESH_INTERVAL,
  });
}
