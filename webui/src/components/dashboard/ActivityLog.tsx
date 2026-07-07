/**
 * ActivityLog Component
 * ======================
 * Time-stamped event feed showing recent system activity.
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
import type { ActivityEntry } from "@/types/api";

interface ActivityLogProps {
  entries?: ActivityEntry[];
}

const defaultEntries: ActivityEntry[] = [
  {
    id: "1",
    timestamp: new Date(Date.now() - 300000).toISOString(),
    message: "Backup job completed (daily-media)",
    type: "backup",
  },
  {
    id: "2",
    timestamp: new Date(Date.now() - 1200000).toISOString(),
    message: "Container plex restarted",
    type: "container",
  },
  {
    id: "3",
    timestamp: new Date(Date.now() - 2400000).toISOString(),
    message: "Snapshot tank/media@auto created",
    type: "snapshot",
  },
  {
    id: "4",
    timestamp: new Date(Date.now() - 3600000).toISOString(),
    message: "User login (admin)",
    type: "login",
  },
  {
    id: "5",
    timestamp: new Date(Date.now() - 7200000).toISOString(),
    message: "System update check completed",
    type: "update",
  },
];

const typeIcons: Record<ActivityEntry["type"], typeof Shield> = {
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

export function ActivityLog({ entries = defaultEntries }: ActivityLogProps) {
  return (
    <div className="rounded-[8px] border border-mk-border bg-mk-surface p-4">
      <h3 className="text-sm font-semibold text-mk-text-primary mb-3">
        Activity Log
      </h3>
      <div className="flex flex-col gap-2">
        {entries.map((entry) => {
          const Icon = typeIcons[entry.type];
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
    </div>
  );
}
