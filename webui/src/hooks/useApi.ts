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

// ─── Firewall Rules ──────────────────────────────────────────────────

export interface FirewallRule {
  id: string;
  chain: string;
  source: string;
  dest: string;
  port: string;
  action: string;
}

export function useFirewallRules() {
  return useSWR<FirewallRule[]>(
    "/network/firewall",
    fetcher,
    { refreshInterval: DATA_REFRESH_INTERVAL }
  );
}

// ─── WireGuard Peers ─────────────────────────────────────────────────

export interface WireGuardPeer {
  name: string;
  publicKey: string;
  endpoint: string;
  lastSeen: string;
}

export interface WireGuardInterface {
  name: string;
  peers: WireGuardPeer[];
}

export function useWireGuardPeers() {
  return useSWR<WireGuardInterface[]>(
    "/network/wireguard",
    fetcher,
    { refreshInterval: DATA_REFRESH_INTERVAL }
  );
}

// ─── DNS Config ──────────────────────────────────────────────────────

export interface DNSConfig {
  primary: string;
  secondary: string;
  search_domain: string;
  overrides: Array<{ hostname: string; ip: string }>;
}

export function useDNSConfig() {
  return useSWR<DNSConfig>(
    "/network/dns",
    fetcher,
    { refreshInterval: DATA_REFRESH_INTERVAL }
  );
}

// ─── Proxy Sites ─────────────────────────────────────────────────────

export interface ProxySite {
  domain: string;
  backend: string;
  ssl: string;
  status: string;
}

export function useProxySites() {
  return useSWR<ProxySite[]>(
    "/network/proxy",
    fetcher,
    { refreshInterval: DATA_REFRESH_INTERVAL }
  );
}

// ─── Protection: Backup Jobs ─────────────────────────────────────────

export interface BackupJob {
  name: string;
  source: string;
  dest: string;
  schedule: string;
  status: string;
  lastRun: string;
  nextRun: string;
}

export function useProtectionJobs() {
  return useSWR<BackupJob[]>(
    "/protection/jobs",
    fetcher,
    { refreshInterval: DATA_REFRESH_INTERVAL }
  );
}

// ─── Protection: Scrubs ──────────────────────────────────────────────

export interface ScrubSchedule {
  pool: string;
  schedule: string;
  lastRun: string;
  duration: string;
  errors: number;
}

export function useProtectionScrubs() {
  return useSWR<ScrubSchedule[]>(
    "/protection/scrubs/all",
    fetcher,
    { refreshInterval: DATA_REFRESH_INTERVAL }
  );
}

// ─── Protection: Replication ─────────────────────────────────────────

export interface ReplicationTask {
  task: string;
  source: string;
  target: string;
  status: string;
  lag: string;
}

export function useProtectionReplication() {
  return useSWR<ReplicationTask[]>(
    "/protection/replication",
    fetcher,
    { refreshInterval: DATA_REFRESH_INTERVAL }
  );
}

// ─── Protection: Retention ───────────────────────────────────────────

export interface RetentionPolicy {
  name: string;
  keepDaily: number;
  keepWeekly: number;
  keepMonthly: number;
}

export function useProtectionRetention() {
  return useSWR<RetentionPolicy[]>(
    "/protection/retention",
    fetcher,
    { refreshInterval: DATA_REFRESH_INTERVAL }
  );
}

// ─── Media: Drives ───────────────────────────────────────────────────

export interface MediaDrive {
  device: string;
  type: string;
  label: string;
  status: string;
}

export function useMediaDrives() {
  return useSWR<MediaDrive[]>(
    "/media/drives",
    fetcher,
    { refreshInterval: DATA_REFRESH_INTERVAL }
  );
}

// ─── Media: Rip Status ──────────────────────────────────────────────

export interface RipStatus {
  active: boolean;
  device?: string;
  title?: string;
  progress?: number;
  eta?: string;
}

export function useMediaRipStatus() {
  return useSWR<RipStatus>(
    "/media/rip/status",
    fetcher,
    { refreshInterval: METRICS_REFRESH_INTERVAL }
  );
}

// ─── System Updates ──────────────────────────────────────────────────

export interface SystemUpdates {
  available: number;
  packages: Array<{ name: string; current: string; available: string }>;
  last_check: string;
}

export function useSystemUpdates() {
  return useSWR<SystemUpdates>(
    "/system/updates",
    fetcher,
    { refreshInterval: DATA_REFRESH_INTERVAL }
  );
}

// ─── AI Settings ─────────────────────────────────────────────────────

export interface AISettings {
  model: string;
  provider: string;
  temperature: number;
  max_tokens: number;
  system_prompt: string;
}

export function useAISettings() {
  return useSWR<AISettings>(
    "/system/ai/settings",
    fetcher,
    { refreshInterval: DATA_REFRESH_INTERVAL }
  );
}


// ─── Chat: Context-Aware Suggestions ─────────────────────────────────

import type { SuggestionsResponse } from "@/types/chat";
import { suggestionsKey } from "@/lib/chat";

/**
 * Fetch context-aware chat suggestions for the current page/selection.
 * Suggestions change rarely, so this uses a long dedupe window and does not
 * poll. Returns `undefined` data while loading or on error; callers should
 * fall back to a sensible static set so the UI is never empty.
 */
export function useChatSuggestions(page: string, selection?: string) {
  return useSWR<SuggestionsResponse>(suggestionsKey(page, selection), fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 60_000,
    shouldRetryOnError: false,
  });
}
