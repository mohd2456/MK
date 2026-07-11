/**
 * useMetrics Hook
 * ================
 * Provides real-time system metrics via WebSocket metric_update events.
 * Falls back to SWR polling via useDashboardSummary when the WebSocket
 * is disconnected.
 */

import { useEffect, useState, useCallback } from "react";
import { useWebSocket } from "./useWebSocket";
import { useDashboardSummary, type DashboardSummaryResponse } from "./useApi";
import type { WSMessage } from "@/lib/ws";

interface MetricsData {
  cpuPercent: number;
  ramPercent: number;
  ramUsedGb: number;
  ramTotalGb: number;
  networkInMbps: number;
  networkOutMbps: number;
  diskPercent: number;
  diskUsedTb: number;
  diskTotalTb: number;
  uptimeSeconds: number;
}

interface UseMetricsReturn {
  /** Current system metrics */
  metrics: MetricsData | null;
  /** Whether metrics are from real-time WebSocket vs polling */
  isRealtime: boolean;
  /** Whether data is still loading */
  isLoading: boolean;
}

function mapSummaryToMetrics(data: DashboardSummaryResponse): MetricsData {
  return {
    cpuPercent: data.cpu_percent,
    ramPercent: data.ram_percent,
    ramUsedGb: data.ram_used_gb,
    ramTotalGb: data.ram_total_gb,
    networkInMbps: data.network_in_mbps,
    networkOutMbps: data.network_out_mbps,
    diskPercent: data.disk_percent,
    diskUsedTb: data.disk_used_tb,
    diskTotalTb: data.disk_total_tb,
    uptimeSeconds: data.uptime_seconds,
  };
}

export function useMetrics(): UseMetricsReturn {
  const { onMessage, isConnected } = useWebSocket();
  const { data: summaryData, isLoading: swrLoading } = useDashboardSummary();
  const [realtimeMetrics, setRealtimeMetrics] = useState<MetricsData | null>(null);

  // Listen for real-time metric updates via WebSocket
  useEffect(() => {
    if (!isConnected) {
      setRealtimeMetrics(null);
      return;
    }

    const unsub = onMessage((msg: WSMessage) => {
      if (msg.type === "metric_update") {
        const data = msg as WSMessage & Partial<DashboardSummaryResponse>;
        // Use functional updater to avoid stale closure over realtimeMetrics
        setRealtimeMetrics((prev) => ({
          cpuPercent: data.cpu_percent ?? prev?.cpuPercent ?? 0,
          ramPercent: data.ram_percent ?? prev?.ramPercent ?? 0,
          ramUsedGb: data.ram_used_gb ?? prev?.ramUsedGb ?? 0,
          ramTotalGb: data.ram_total_gb ?? prev?.ramTotalGb ?? 0,
          networkInMbps: data.network_in_mbps ?? prev?.networkInMbps ?? 0,
          networkOutMbps: data.network_out_mbps ?? prev?.networkOutMbps ?? 0,
          diskPercent: data.disk_percent ?? prev?.diskPercent ?? 0,
          diskUsedTb: data.disk_used_tb ?? prev?.diskUsedTb ?? 0,
          diskTotalTb: data.disk_total_tb ?? prev?.diskTotalTb ?? 0,
          uptimeSeconds: data.uptime_seconds ?? prev?.uptimeSeconds ?? 0,
        }));
      }
    });

    return unsub;
  }, [isConnected, onMessage]);

  // Determine which metrics source to use
  const getMetrics = useCallback((): MetricsData | null => {
    if (realtimeMetrics && isConnected) {
      return realtimeMetrics;
    }
    if (summaryData) {
      return mapSummaryToMetrics(summaryData);
    }
    return null;
  }, [realtimeMetrics, isConnected, summaryData]);

  return {
    metrics: getMetrics(),
    isRealtime: isConnected && realtimeMetrics !== null,
    isLoading: swrLoading && !realtimeMetrics,
  };
}
