/**
 * DropFolderList Component
 * =========================
 * Shows all configured drop folders with their status,
 * item count, and toggle to enable/disable watching.
 */

import {
  FolderOpen,
  Film,
  Tv,
  Music,
  HelpCircle,
  Eye,
  EyeOff,
  MoreHorizontal,
  Plus,
} from "lucide-react";
import { cn, formatRelativeTime } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Toggle } from "@/components/ui/toggle";
import { DropdownMenu, DropdownItem, DropdownSeparator } from "@/components/ui/dropdown-menu";
import type { DropFolder, MediaCategory } from "@/types/drop-folders";

interface DropFolderListProps {
  folders?: DropFolder[];
  onToggleWatch?: (id: string, enabled: boolean) => void;
  onAddFolder?: () => void;
}

const categoryIcon: Record<MediaCategory | "auto", typeof Film> = {
  movie: Film,
  tv_show: Tv,
  music: Music,
  unknown: HelpCircle,
  auto: FolderOpen,
};

const categoryLabel: Record<MediaCategory | "auto", string> = {
  movie: "Movies",
  tv_show: "TV Shows",
  music: "Music",
  unknown: "Unknown",
  auto: "Auto-detect",
};

const defaultFolders: DropFolder[] = [
  {
    id: "df-1",
    name: "Movie Drops",
    path: "/mnt/drops/movies",
    media_type: "movie",
    enabled: true,
    watch_enabled: true,
    items_pending: 2,
    last_activity: new Date(Date.now() - 1200000).toISOString(),
  },
  {
    id: "df-2",
    name: "TV Show Drops",
    path: "/mnt/drops/tv",
    media_type: "tv_show",
    enabled: true,
    watch_enabled: true,
    items_pending: 5,
    last_activity: new Date(Date.now() - 300000).toISOString(),
  },
  {
    id: "df-3",
    name: "Music Drops",
    path: "/mnt/drops/music",
    media_type: "music",
    enabled: true,
    watch_enabled: true,
    items_pending: 0,
    last_activity: new Date(Date.now() - 7200000).toISOString(),
  },
  {
    id: "df-4",
    name: "General Drop",
    path: "/mnt/drops/incoming",
    media_type: "auto",
    enabled: true,
    watch_enabled: false,
    items_pending: 3,
    last_activity: new Date(Date.now() - 600000).toISOString(),
  },
];

export function DropFolderList({
  folders = defaultFolders,
  onToggleWatch,
  onAddFolder,
}: DropFolderListProps) {
  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold text-mk-text-primary">Drop Folders</h3>
          <p className="text-xs text-mk-text-muted mt-0.5">
            Drop media files here. MK will identify, organize, and deliver to your libraries.
          </p>
        </div>
        <Button size="sm" onClick={onAddFolder}>
          <Plus size={14} />
          Add Folder
        </Button>
      </div>

      {/* Folder cards */}
      {folders.map((folder) => {
        const Icon = categoryIcon[folder.media_type];
        return (
          <div
            key={folder.id}
            className={cn(
              "rounded-[8px] border border-mk-border bg-mk-surface p-4",
              "hover:border-mk-border-strong transition-colors duration-200",
              !folder.enabled && "opacity-50"
            )}
          >
            <div className="flex items-start justify-between gap-3">
              {/* Left: Icon + Info */}
              <div className="flex items-start gap-3 min-w-0 flex-1">
                <div className="w-9 h-9 rounded-[8px] bg-mk-elevated border border-mk-border flex items-center justify-center shrink-0">
                  <Icon size={16} className="text-mk-accent" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <h4 className="text-sm font-medium text-mk-text-primary truncate">
                      {folder.name}
                    </h4>
                    <Badge variant="default">{categoryLabel[folder.media_type]}</Badge>
                    {folder.items_pending > 0 && (
                      <Badge variant="accent">{folder.items_pending} pending</Badge>
                    )}
                  </div>
                  <p className="text-xs text-mk-text-muted font-mono mt-0.5 truncate">
                    {folder.path}
                  </p>
                  <p className="text-[11px] text-mk-text-muted mt-1">
                    Last activity: {formatRelativeTime(folder.last_activity)}
                  </p>
                </div>
              </div>

              {/* Right: Watch toggle + actions */}
              <div className="flex items-center gap-2 shrink-0">
                <Toggle
                  checked={folder.watch_enabled}
                  onCheckedChange={(checked) => onToggleWatch?.(folder.id, checked)}
                  label={folder.watch_enabled ? "Watching" : "Paused"}
                />
                <DropdownMenu
                  trigger={
                    <Button variant="ghost" size="icon-sm">
                      <MoreHorizontal size={14} />
                    </Button>
                  }
                >
                  <DropdownItem>Edit Folder</DropdownItem>
                  <DropdownItem>Process Now</DropdownItem>
                  <DropdownItem>View History</DropdownItem>
                  <DropdownSeparator />
                  <DropdownItem destructive>Remove Folder</DropdownItem>
                </DropdownMenu>
              </div>
            </div>

            {/* Watch indicator */}
            {folder.watch_enabled && (
              <div className="flex items-center gap-1.5 mt-2 pt-2 border-t border-mk-border">
                <Eye size={11} className="text-mk-success" />
                <span className="text-[10px] text-mk-success font-medium">
                  Live watching for new files
                </span>
              </div>
            )}
            {!folder.watch_enabled && folder.enabled && (
              <div className="flex items-center gap-1.5 mt-2 pt-2 border-t border-mk-border">
                <EyeOff size={11} className="text-mk-text-muted" />
                <span className="text-[10px] text-mk-text-muted">
                  Manual processing only
                </span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
