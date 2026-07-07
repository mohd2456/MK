/**
 * HealthSummary Component
 * ========================
 * Quick overview of system health with color-coded dots.
 */

import { cn } from "@/lib/utils";
import {
  HardDrive,
  Network,
  Container,
  Shield,
  Thermometer,
} from "lucide-react";

interface HealthItem {
  label: string;
  value: string;
  status: "healthy" | "degraded" | "critical";
  icon: React.ReactNode;
}

interface HealthSummaryProps {
  items?: HealthItem[];
}

const defaultItems: HealthItem[] = [
  {
    label: "Storage",
    value: "Healthy",
    status: "healthy",
    icon: <HardDrive size={14} />,
  },
  {
    label: "Network",
    value: "2 interfaces",
    status: "healthy",
    icon: <Network size={14} />,
  },
  {
    label: "Apps",
    value: "12/12 running",
    status: "healthy",
    icon: <Container size={14} />,
  },
  {
    label: "Backups",
    value: "Last 2h ago",
    status: "healthy",
    icon: <Shield size={14} />,
  },
  {
    label: "Temp",
    value: "42C (normal)",
    status: "healthy",
    icon: <Thermometer size={14} />,
  },
];

const statusDotColor = {
  healthy: "bg-mk-success",
  degraded: "bg-mk-warning",
  critical: "bg-mk-error",
};

export function HealthSummary({ items = defaultItems }: HealthSummaryProps) {
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
