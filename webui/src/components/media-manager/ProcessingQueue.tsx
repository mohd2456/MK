/**
 * ProcessingQueue Component
 * ==========================
 * Real-time view of items MK is currently processing:
 * identifying, organizing, and delivering to Jellyfin/Plex libraries.
 */

import {
  Film,
  Tv,
  Music,
  HelpCircle,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Loader2,
  Search,
  FolderOutput,
  Clock,
} from "lucide-react";
import { cn, formatBytes, formatRelativeTime } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import type { DropItem, ProcessingStatus, MediaCategory } from "@/types/drop-folders";

interface ProcessingQueueProps {
  items?: DropItem[];
  onRetry?: (id: string) => void;
  onResolve?: (id: string) => void;
  onDismiss?: (id: string) => void;
}

const statusConfig: Record<
  ProcessingStatus,
  { label: string; icon: typeof CheckCircle2; color: string; badge: "default" | "success" | "warning" | "error" | "info" | "accent" }
> = {
  pending: { label: "Pending", icon: Clock, color: "text-mk-text-muted", badge: "default" },
  identifying: { label: "Identifying", icon: Search, color: "text-mk-info", badge: "info" },
  organizing: { label: "Organizing", icon: FolderOutput, color: "text-mk-accent", badge: "accent" },
  complete: { label: "Complete", icon: CheckCircle2, color: "text-mk-success", badge: "success" },
  failed: { label: "Failed", icon: XCircle, color: "text-mk-error", badge: "error" },
  manual_review: { label: "Needs Review", icon: AlertTriangle, color: "text-mk-warning", badge: "warning" },
};

const categoryIcon: Record<MediaCategory, typeof Film> = {
  movie: Film,
  tv_show: Tv,
  music: Music,
  unknown: HelpCircle,
};

const defaultItems: DropItem[] = [
  {
    id: "di-1",
    filename: "Oppenheimer.2023.2160p.UHD.BluRay.x265.mkv",
    original_path: "/mnt/drops/movies/Oppenheimer.2023.2160p.UHD.BluRay.x265.mkv",
    size_bytes: 58.2 * 1024 ** 3,
    detected_type: "movie",
    status: "organizing",
    progress_percent: 72,
    dropped_at: new Date(Date.now() - 180000).toISOString(),
    metadata: { title: "Oppenheimer", year: 2023, tmdb_id: 872585 },
  },
  {
    id: "di-2",
    filename: "Breaking.Bad.S01E01.720p.BluRay.mkv",
    original_path: "/mnt/drops/tv/Breaking.Bad.S01E01.720p.BluRay.mkv",
    size_bytes: 4.2 * 1024 ** 3,
    detected_type: "tv_show",
    status: "identifying",
    progress_percent: 30,
    dropped_at: new Date(Date.now() - 60000).toISOString(),
    metadata: { title: "Breaking Bad", series_name: "Breaking Bad", season: 1, episode: 1, episode_title: "Pilot" },
  },
  {
    id: "di-3",
    filename: "Kendrick Lamar - Not Like Us.flac",
    original_path: "/mnt/drops/music/Kendrick Lamar - Not Like Us.flac",
    size_bytes: 42 * 1024 ** 2,
    detected_type: "music",
    status: "complete",
    progress_percent: 100,
    dropped_at: new Date(Date.now() - 600000).toISOString(),
    processed_at: new Date(Date.now() - 540000).toISOString(),
    metadata: { title: "Not Like Us", artist: "Kendrick Lamar", album: "GNX", track_number: 1, genre: "Hip-Hop" },
    destination_path: "/mnt/media/music/Kendrick Lamar/GNX/01 - Not Like Us.flac",
  },
  {
    id: "di-4",
    filename: "Breaking.Bad.S01E02.720p.BluRay.mkv",
    original_path: "/mnt/drops/tv/Breaking.Bad.S01E02.720p.BluRay.mkv",
    size_bytes: 3.8 * 1024 ** 3,
    detected_type: "tv_show",
    status: "pending",
    progress_percent: 0,
    dropped_at: new Date(Date.now() - 45000).toISOString(),
    metadata: { title: "Breaking Bad", series_name: "Breaking Bad", season: 1, episode: 2, episode_title: "Cat's in the Bag..." },
  },
  {
    id: "di-5",
    filename: "random_video_2024_final_v2.mp4",
    original_path: "/mnt/drops/incoming/random_video_2024_final_v2.mp4",
    size_bytes: 1.5 * 1024 ** 3,
    detected_type: "unknown",
    status: "manual_review",
    progress_percent: 0,
    dropped_at: new Date(Date.now() - 900000).toISOString(),
    error_message: "Could not identify media type or match to any known title. Please categorize manually.",
  },
  {
    id: "di-6",
    filename: "The.Departed.2006.1080p.BluRay.REMUX.mkv",
    original_path: "/mnt/drops/movies/The.Departed.2006.1080p.BluRay.REMUX.mkv",
    size_bytes: 32 * 1024 ** 3,
    detected_type: "movie",
    status: "failed",
    progress_percent: 0,
    dropped_at: new Date(Date.now() - 1800000).toISOString(),
    error_message: "Destination path /mnt/media/movies is full. Free up space or change destination.",
  },
];

export function ProcessingQueue({
  items = defaultItems,
  onRetry,
  onResolve,
  onDismiss,
}: ProcessingQueueProps) {
  // Sort: active items first, then pending, then completed/failed
  const sortedItems = [...items].sort((a, b) => {
    const order: Record<ProcessingStatus, number> = {
      identifying: 0,
      organizing: 1,
      pending: 2,
      manual_review: 3,
      failed: 4,
      complete: 5,
    };
    return order[a.status] - order[b.status];
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold text-mk-text-primary">Processing Queue</h3>
          <p className="text-xs text-mk-text-muted mt-0.5">
            MK is identifying and organizing your media files.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="accent">
            {items.filter((i) => i.status === "identifying" || i.status === "organizing").length} active
          </Badge>
          <Badge variant="default">
            {items.filter((i) => i.status === "pending").length} queued
          </Badge>
        </div>
      </div>

      {/* Queue items */}
      <div className="space-y-2">
        {sortedItems.map((item) => {
          const status = statusConfig[item.status];
          const StatusIcon = status.icon;
          const TypeIcon = categoryIcon[item.detected_type];
          const isActive = item.status === "identifying" || item.status === "organizing";

          return (
            <div
              key={item.id}
              className={cn(
                "rounded-[8px] border bg-mk-surface p-3",
                "transition-all duration-200",
                isActive
                  ? "border-mk-accent/30 bg-mk-accent/[0.02]"
                  : "border-mk-border hover:border-mk-border-strong"
              )}
            >
              <div className="flex items-start gap-3">
                {/* Type icon */}
                <div className={cn(
                  "w-8 h-8 rounded-[6px] flex items-center justify-center shrink-0 mt-0.5",
                  "bg-mk-elevated border border-mk-border"
                )}>
                  <TypeIcon size={14} className="text-mk-text-secondary" />
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm text-mk-text-primary font-medium truncate">
                      {item.metadata?.title ?? item.filename}
                    </p>
                    <Badge variant={status.badge}>
                      <StatusIcon size={10} className={cn("mr-1", isActive && "animate-spin")} />
                      {status.label}
                    </Badge>
                  </div>

                  {/* Metadata line */}
                  <p className="text-xs text-mk-text-muted mt-0.5 truncate">
                    {item.detected_type === "tv_show" && item.metadata?.season != null && (
                      <span>S{String(item.metadata.season).padStart(2, "0")}E{String(item.metadata.episode).padStart(2, "0")} &middot; </span>
                    )}
                    {item.detected_type === "music" && item.metadata?.artist && (
                      <span>{item.metadata.artist} &middot; </span>
                    )}
                    <span>{formatBytes(item.size_bytes)}</span>
                    <span> &middot; dropped {formatRelativeTime(item.dropped_at)}</span>
                  </p>

                  {/* Progress bar for active items */}
                  {isActive && (
                    <div className="mt-2">
                      <Progress value={item.progress_percent} variant="accent" size="sm" showLabel />
                    </div>
                  )}

                  {/* Destination for completed */}
                  {item.status === "complete" && item.destination_path && (
                    <p className="text-[11px] text-mk-success font-mono mt-1.5 truncate">
                      &rarr; {item.destination_path}
                    </p>
                  )}

                  {/* Error for failed */}
                  {(item.status === "failed" || item.status === "manual_review") && item.error_message && (
                    <p className="text-[11px] text-mk-error mt-1.5">
                      {item.error_message}
                    </p>
                  )}
                </div>

                {/* Actions */}
                <div className="flex items-center gap-1 shrink-0">
                  {item.status === "failed" && (
                    <Button variant="ghost" size="icon-sm" onClick={() => onRetry?.(item.id)} aria-label="Retry">
                      <Loader2 size={13} />
                    </Button>
                  )}
                  {item.status === "manual_review" && (
                    <Button variant="accent_ghost" size="icon-sm" onClick={() => onResolve?.(item.id)} aria-label="Resolve">
                      <AlertTriangle size={13} />
                    </Button>
                  )}
                  {(item.status === "complete" || item.status === "failed") && (
                    <Button variant="ghost" size="icon-sm" onClick={() => onDismiss?.(item.id)} aria-label="Dismiss">
                      <XCircle size={13} className="text-mk-text-muted" />
                    </Button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {items.length === 0 && (
        <div className="text-center py-8 text-mk-text-muted text-sm">
          No items in queue. Drop files into a watch folder to get started.
        </div>
      )}
    </div>
  );
}
