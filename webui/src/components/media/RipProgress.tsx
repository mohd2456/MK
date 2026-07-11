/**
 * RipProgress Component
 * ======================
 * Displays rip progress with a progress bar, ETA, speed, and current operation.
 */

import { Progress } from "@/components/ui/progress";
import { formatDuration } from "@/lib/utils";
import type { RipProgress as RipProgressType } from "@/types/media";

interface RipProgressProps {
  progress: RipProgressType;
}

export function RipProgress({ progress }: RipProgressProps) {
  if (!progress.active) {
    return (
      <p className="text-sm text-mk-text-muted p-4">No rip in progress.</p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-sm">
        <span className="text-mk-text-primary font-medium">{progress.title}</span>
        <span className="text-mk-text-muted text-xs">
          Title {progress.current_title}/{progress.total_titles}
        </span>
      </div>

      <Progress
        value={progress.progress_percent}
        variant="accent"
        size="lg"
        showLabel
      />

      <div className="flex items-center justify-between text-xs text-mk-text-muted">
        <span>
          ETA: {formatDuration(progress.eta_seconds)} ({progress.speed_mbps} MB/s)
        </span>
        <span className="font-mono">{progress.output_path}</span>
      </div>
    </div>
  );
}
