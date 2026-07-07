/**
 * ActivityLog Component
 * ======================
 * Time-stamped event feed showing recent system activity.
 * Fetches real data from /api/v1/dashboard/activity.
 */

import {
  Shield,
  Container,
  Camera,
  LogIn,
  Server,
  Download,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useDashboardActivity } from "@/hooks/useApi";

const typeIcons: Record<string, typeof Shield> = {
  backup: Shield,
  container: Container,
  snapshot: Camera,
  login: LogIn,
  system: Server,
  update: Download,
};

function formatTime(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function ActivityLog() {
  const { data, isLoading } = useDashboardActivity();

  const entries = data?.events ?? [];

  return (
    <div className="rounded-[8px] border border-mk-border bg-mk-surface p-4">
      <h3 className="text-sm font-semibold text-mk-text-primary mb-3">
        Activity Log
      </h3>

      {isLoading ? (
        <p className="text-sm text-mk-text-muted py-2">Loading activity...</p>
      ) : entries.length === 0 ? (
        <p className="text-sm text-mk-text-muted py-2">No recent activity</p>
      ) : (
        <div className="flex flex-col gap-2">
          {entries.map((entry) => {
            const Icon = typeIcons[entry.type] ?? Server;
            return (
              <div key={entry.id} className="flex items-start gap-2.5">
                {/* Timestamp */}
                <span className="text-xs text-mk-text-muted font-mono shrink-0 w-11 pt-0.5">
                  {formatTime(entry.timestamp)}
                </span>
                {/* Icon */}
                <Icon
                  size={13}
                  className={cn("shrink-0 mt-0.5 text-mk-text-muted")}
                />
                {/* Message */}
                <span className="text-sm text-mk-text-secondary leading-snug">
                  {entry.message}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
