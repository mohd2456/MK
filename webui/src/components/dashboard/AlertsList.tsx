/**
 * AlertsList Component
 * =====================
 * Prioritized list of system alerts with severity indicators.
 * Fetches real alerts from /api/v1/dashboard/alerts.
 */

import { AlertTriangle, AlertCircle, Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDashboardAlerts } from "@/hooks/useApi";

type AlertSeverity = "critical" | "warning" | "info";

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

export function AlertsList() {
  const { data: alerts, isLoading } = useDashboardAlerts();

  const activeAlerts = alerts ?? [];

  return (
    <div className="rounded-[8px] border border-mk-border bg-mk-surface p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-mk-text-primary">
          Alerts ({activeAlerts.length})
        </h3>
      </div>

      {isLoading ? (
        <p className="text-sm text-mk-text-muted py-2">Loading alerts...</p>
      ) : activeAlerts.length === 0 ? (
        <p className="text-sm text-mk-text-muted py-2">No active alerts</p>
      ) : (
        <div className="flex flex-col gap-2">
          {activeAlerts.map((alert) => {
            const severity = (alert.severity as AlertSeverity) || "info";
            const config = severityConfig[severity] ?? severityConfig.info;
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
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
