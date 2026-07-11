/**
 * InterfaceCard Component
 * ========================
 * Displays a network interface with name, type, IP, speed, and status badge.
 */

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import type { NetworkInterface } from "@/types/network";

interface InterfaceCardProps {
  iface: NetworkInterface;
}

const statusVariant: Record<string, "success" | "warning" | "error"> = {
  connected: "success",
  up: "success",
  disconnected: "error",
  down: "error",
};

export function InterfaceCard({ iface }: InterfaceCardProps) {
  return (
    <div
      className={cn(
        "rounded-[8px] border border-mk-border bg-mk-surface p-4",
        "hover:border-mk-border-strong transition-colors duration-200"
      )}
    >
      <div className="flex items-start justify-between mb-2">
        <div>
          <h4 className="text-sm font-semibold text-mk-text-primary font-mono">
            {iface.name}
          </h4>
          <p className="text-xs text-mk-text-muted mt-0.5">{iface.type}</p>
        </div>
        <Badge variant={statusVariant[iface.status] ?? "success"}>
          {iface.status}
        </Badge>
      </div>

      <div className="space-y-1.5 text-xs">
        <div className="flex items-center justify-between">
          <span className="text-mk-text-muted">IP</span>
          <span className="text-mk-text-primary font-mono">{iface.ip_address}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-mk-text-muted">Speed</span>
          <span className="text-mk-text-primary">{iface.speed}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-mk-text-muted">MAC</span>
          <span className="text-mk-text-primary font-mono">{iface.mac_address}</span>
        </div>
      </div>
    </div>
  );
}
