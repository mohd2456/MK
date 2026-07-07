/**
 * HealthSummary Component
 * ========================
 * Quick overview of system health with color-coded dots.
 * Fetches real data from the dashboard summary API.
 */

import { cn } from "@/lib/utils";
import {
  HardDrive,
  Network,
  Container,
  Shield,
  Thermometer,
} from "lucide-react";
import { useDashboardSummary } from "@/hooks/useApi";

interface HealthItem {
  label: string;
  value: string;
  status: "healthy" | "degraded" | "critical";
  icon: React.ReactNode;
}

const statusDotColor = {
  healthy: "bg-mk-success",
  degraded: "bg-mk-warning",
  critical: "bg-mk-error",
};

function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  if (days > 0) return `${days}d ${hours}h`;
  const mins = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${mins}m`;
}

export function HealthSummary() {
  const { data, isLoading } = useDashboardSummary();

  const items: HealthItem[] = [
    {
      label: "Storage",
      value: isLoading
        ? "Loading..."
        : data
          ? data.disk_percent >= 90
            ? `${Math.round(data.disk_percent)}% (critical)`
            : data.disk_percent >= 80
              ? `${Math.round(data.disk_percent)}% (filling)`
              : "Healthy"
          : "Unknown",
      status: data
        ? data.disk_percent >= 90
          ? "critical"
          : data.disk_percent >= 80
            ? "degraded"
            : "healthy"
        : "healthy",
      icon: <HardDrive size={14} />,
    },
    {
      label: "Network",
      value: isLoading
        ? "Loading..."
        : data?.tailscale_connected
          ? `Tailscale (${data.tailscale_ip})`
          : "Local only",
      status: data?.tailscale_connected ? "healthy" : "degraded",
      icon: <Network size={14} />,
    },
    {
      label: "Apps",
      value: isLoading
        ? "Loading..."
        : data
          ? `${data.containers_running}/${data.containers_total} running`
          : "Unknown",
      status: data
        ? data.containers_running === data.containers_total
          ? "healthy"
          : data.containers_running === 0
            ? "critical"
            : "degraded"
        : "healthy",
      icon: <Container size={14} />,
    },
    {
      label: "Uptime",
      value: isLoading
        ? "Loading..."
        : data
          ? formatUptime(data.uptime_seconds)
          : "Unknown",
      status: "healthy",
      icon: <Shield size={14} />,
    },
    {
      label: "RAM",
      value: isLoading
        ? "Loading..."
        : data
          ? data.ram_percent >= 90
            ? `${Math.round(data.ram_percent)}% (high)`
            : `${Math.round(data.ram_percent)}% (ok)`
          : "Unknown",
      status: data
        ? data.ram_percent >= 90
          ? "critical"
          : data.ram_percent >= 80
            ? "degraded"
            : "healthy"
        : "healthy",
      icon: <Thermometer size={14} />,
    },
  ];

  return (
    <div className="rounded-[8px] border border-mk-border bg-mk-surface p-4">
      <h3 className="text-sm font-semibold text-mk-text-primary mb-3">
        Health Summary
      </h3>
      <div className="flex flex-col gap-2.5">
        {items.map((item) => (
          <div key={item.label} className="flex items-center gap-2.5">
            {/* Status dot */}
            <span
              className={cn(
                "w-2 h-2 rounded-full shrink-0",
                statusDotColor[item.status]
              )}
            />
            {/* Icon */}
            <span className="text-mk-text-muted shrink-0">{item.icon}</span>
            {/* Label */}
            <span className="text-sm text-mk-text-secondary flex-1">
              {item.label}
            </span>
            {/* Value */}
            <span className="text-sm text-mk-text-primary font-medium">
              {item.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
