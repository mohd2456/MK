/**
 * DropFolderStats Component
 * ==========================
 * Summary statistics for the drop folder system.
 */

import {
  CheckCircle2,
  Clock,
  XCircle,
  AlertTriangle,
  TrendingUp,
  HardDrive,
} from "lucide-react";
import { formatBytes } from "@/lib/utils";
import type { DropFolderStats as StatsType } from "@/types/drop-folders";

interface DropFolderStatsProps {
  stats?: StatsType;
}

const defaultStats: StatsType = {
  total_processed: 1847,
  processed_today: 12,
  pending_count: 10,
  failed_count: 1,
  manual_review_count: 1,
  total_size_processed_bytes: 4.2 * 1024 ** 4,
};

export function DropFolderStats({ stats = defaultStats }: DropFolderStatsProps) {
  const statCards = [
    {
      label: "Processed Today",
      value: stats.processed_today,
      icon: TrendingUp,
      color: "text-mk-accent",
    },
    {
      label: "Pending",
      value: stats.pending_count,
      icon: Clock,
      color: "text-mk-info",
    },
    {
      label: "Total Processed",
      value: stats.total_processed.toLocaleString(),
      icon: CheckCircle2,
      color: "text-mk-success",
    },
    {
      label: "Total Size Moved",
      value: formatBytes(stats.total_size_processed_bytes),
      icon: HardDrive,
      color: "text-mk-text-secondary",
    },
    {
      label: "Failed",
      value: stats.failed_count,
      icon: XCircle,
      color: "text-mk-error",
    },
    {
      label: "Needs Review",
      value: stats.manual_review_count,
      icon: AlertTriangle,
      color: "text-mk-warning",
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      {statCards.map((card) => {
        const Icon = card.icon;
        return (
          <div
            key={card.label}
            className="rounded-[8px] border border-mk-border bg-mk-surface p-3 text-center"
          >
            <Icon size={16} className={`${card.color} mx-auto mb-1.5`} />
            <p className="text-lg font-bold text-mk-text-primary">{card.value}</p>
            <p className="text-[10px] text-mk-text-muted mt-0.5">{card.label}</p>
          </div>
        );
      })}
    </div>
  );
}
