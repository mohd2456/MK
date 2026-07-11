/**
 * DriveStatus Component
 * ======================
 * Displays optical drive information including device, model, state, and disc details.
 */

import { Disc3 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { OpticalDrive } from "@/types/media";

interface DriveStatusProps {
  drive: OpticalDrive;
}

const stateVariant: Record<string, "success" | "warning" | "accent" | "error"> = {
  empty: "warning",
  detecting: "accent",
  disc_detected: "success",
  ripping: "accent",
  ejecting: "warning",
};

const stateLabel: Record<string, string> = {
  empty: "NO DISC",
  detecting: "DETECTING",
  disc_detected: "DISC DETECTED",
  ripping: "RIPPING",
  ejecting: "EJECTING",
};

export function DriveStatus({ drive }: DriveStatusProps) {
  return (
    <div
      className={cn(
        "rounded-[8px] border border-mk-border bg-mk-surface p-4 space-y-3"
      )}
    >
      <div className="flex items-center gap-2">
        <Disc3 size={18} className="text-mk-accent" />
        <span className="text-sm text-mk-text-secondary">
          Drive:{" "}
          <span className="text-mk-text-primary font-mono">{drive.device}</span>{" "}
          ({drive.model})
        </span>
      </div>
      <Badge variant={stateVariant[drive.state] ?? "warning"}>
        {stateLabel[drive.state] ?? drive.state.toUpperCase()}
      </Badge>

      {drive.disc_info && (
        <div
          className={cn(
            "rounded-[8px] border border-mk-border bg-mk-elevated p-3 space-y-1.5"
          )}
        >
          <div className="grid grid-cols-2 gap-y-1 text-xs">
            <span className="text-mk-text-muted">Title:</span>
            <span className="text-mk-text-primary font-medium">
              {drive.disc_info.title}
              {drive.disc_info.year ? ` (${drive.disc_info.year})` : ""}
            </span>
            <span className="text-mk-text-muted">Type:</span>
            <span className="text-mk-text-primary">{drive.disc_info.type}</span>
            <span className="text-mk-text-muted">Titles found:</span>
            <span className="text-mk-text-primary">{drive.disc_info.titles_count}</span>
            <span className="text-mk-text-muted">Main feature:</span>
            <span className="text-mk-text-primary">
              Title {drive.disc_info.main_title_index} ({drive.disc_info.main_title_duration})
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
