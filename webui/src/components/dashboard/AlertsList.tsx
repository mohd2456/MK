/**
 * AlertsList Component
 * =====================
 * Prioritized list of system alerts with severity indicators.
 */

import { AlertTriangle, AlertCircle, Info, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Alert, AlertSeverity } from "@/types/api";

interface AlertsListProps {
  alerts?: Alert[];
  onDismiss?: (id: string) => void;
}

const defaultAlerts: Alert[] = [
  {
    id: "1",
    severity: "warning",
    message: "Disk sda temperature 55C during scrub",
    timestamp: new Date(Date.now() - 3600000).toISOString(),
    dismissed: false,
    source: "storage",
  },
  {
    id: "2",
    severity: "warning",
    message: "Pool tank at 75% capacity",
    timestamp: new Date(Date.now() - 7200000).toISOString(),
    dismissed: false,
    source: "storage",
  },
  {
    id: "3",
    severity: "info",
    message: "System update available (linux-image 6.6.10)",
    timestamp: new Date(Date.now() - 14400000).toISOString(),
    dismissed: false,
    source: "system",
  },
];

const severityConfig: Record<
  AlertSeverity,
  { icon: typeof AlertTriangle; color: string; bgColor: string }
> = {
  critical: {
    icon: AlertCircle,
    color: "text-mk-error",
    bgColor: "bg-mk-error/5",
  },
  warning: {
    icon: AlertTriangle,
    color: "text-mk-warning",
    bgColor: "bg-mk-warning/5",
  },
  info: {
    icon: Info,
    color: "text-mk-info",
    bgColor: "bg-mk-info/5",
  },
};

export function AlertsList({
  alerts = defaultAlerts,
  onDismiss,
}: AlertsListProps) {
  const activeAlerts = alerts.filter((a) => !a.dismissed);

  return (
    <div className="rounded-[8px] border border-mk-border bg-mk-surface p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-mk-text-primary">
          Alerts ({activeAlerts.length})
        </h3>
      </div>

      {activeAlerts.length === 0 ? (
        <p className="text-sm text-mk-text-muted py-2">No active alerts</p>
      ) : (
        <div className="flex flex-col gap-2">
          {activeAlerts.map((alert) => {
            const config = severityConfig[alert.severity];
            const Icon = config.icon;
            return (
              <div
                key={alert.id}
                className={cn(
                  "flex items-start gap-2.5 p-2.5 rounded-[4px]",
                  config.bgColor,
                  "group"
                )}
              >
                <Icon size={14} className={cn("shrink-0 mt-0.5", config.color)} />
                <span className="text-sm text-mk-text-secondary flex-1 leading-snug">
                  {alert.message}
                </span>
                {onDismiss && (
                  <button
                    onClick={() => onDismiss(alert.id)}
                    className="opacity-0 group-hover:opacity-100 text-mk-text-muted hover:text-mk-text-primary transition-opacity"
                    aria-label="Dismiss alert"
                  >
                    <X size={12} />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
