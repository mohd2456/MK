/**
 * SystemInfo Component
 * =====================
 * Displays key-value system information: hostname, OS, kernel, uptime, CPU, RAM.
 */

import { Card, CardContent } from "@/components/ui/card";
import type { SystemInfoResponse } from "@/hooks/useApi";

interface SystemInfoProps {
  info: SystemInfoResponse;
}

function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days} days ${hours} hours`;
  if (hours > 0) return `${hours} hours ${mins} min`;
  return `${mins} min`;
}

export function SystemInfo({ info }: SystemInfoProps) {
  const fields = [
    { label: "Hostname", value: info.hostname },
    { label: "OS", value: info.os },
    { label: "Kernel", value: info.kernel },
    { label: "Arch", value: info.arch },
    { label: "Uptime", value: formatUptime(info.uptime_seconds) },
    {
      label: "CPU",
      value: info.cpu_model
        ? `${info.cpu_model} (${info.cpu_count}C)`
        : `${info.cpu_count} cores`,
    },
    {
      label: "RAM",
      value: info.ram_total_gb
        ? `${info.ram_total_gb} GB (${info.ram_used_gb} GB used)`
        : "Unknown",
    },
    { label: "Python", value: info.python },
  ];

  return (
    <Card>
      <CardContent className="p-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-y-3 gap-x-8">
          {fields.map((field) => (
            <div key={field.label} className="flex items-baseline gap-2">
              <span className="text-sm text-mk-text-muted min-w-[90px]">
                {field.label}:
              </span>
              <span className="text-sm text-mk-text-primary">{field.value}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
