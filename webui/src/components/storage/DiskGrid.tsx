/**
 * DiskGrid Component
 * ===================
 * Shows physical disks with health info, temperature, and SMART status.
 */

import { cn } from "@/lib/utils";
import { formatBytes } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Thermometer } from "lucide-react";
import type { Disk } from "@/types/storage";

interface DiskGridProps {
  disks?: Disk[];
}

const defaultDisks: Disk[] = [
  { device: "sda", model: "WD Red 12TB", size_bytes: 12 * 1024 ** 4, temperature: 38, smart_status: "PASS", pool: "tank", serial: "WD-ABC123", hours_on: 12400 },
  { device: "sdb", model: "WD Red 12TB", size_bytes: 12 * 1024 ** 4, temperature: 40, smart_status: "PASS", pool: "tank", serial: "WD-DEF456", hours_on: 12380 },
  { device: "sdc", model: "WD Red 12TB", size_bytes: 12 * 1024 ** 4, temperature: 55, smart_status: "WARN", pool: "tank", serial: "WD-GHI789", hours_on: 18900 },
  { device: "nvme0", model: "Samsung 980 Pro", size_bytes: 1 * 1024 ** 4, temperature: 42, smart_status: "PASS", pool: "fast", serial: "S5N-XYZ", hours_on: 5600 },
];

const smartBadge: Record<string, "success" | "warning" | "error"> = {
  PASS: "success",
  WARN: "warning",
  FAIL: "error",
};

function tempColor(temp: number): string {
  if (temp >= 55) return "text-mk-error";
  if (temp >= 45) return "text-mk-warning";
  return "text-mk-text-secondary";
}

export function DiskGrid({ disks = defaultDisks }: DiskGridProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
      {disks.map((disk) => (
        <div
          key={disk.device}
          className={cn(
            "rounded-[8px] border border-mk-border bg-mk-surface p-3",
            "hover:border-mk-border-strong transition-colors"
          )}
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-semibold text-mk-text-primary font-mono">
              {disk.device}
            </span>
            <Badge variant={smartBadge[disk.smart_status]}>
              {disk.smart_status}
            </Badge>
          </div>

          <p className="text-xs text-mk-text-muted truncate mb-2">
            {disk.model}
          </p>

          <div className="flex items-center justify-between">
            <span className="text-xs text-mk-text-muted">
              {formatBytes(disk.size_bytes)}
            </span>
            <span className={cn("flex items-center gap-1 text-xs font-medium", tempColor(disk.temperature))}>
              <Thermometer size={12} />
              {disk.temperature}C
            </span>
          </div>

          {disk.pool && (
            <p className="text-[10px] text-mk-text-muted mt-2 pt-2 border-t border-mk-border">
              Pool: {disk.pool}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
