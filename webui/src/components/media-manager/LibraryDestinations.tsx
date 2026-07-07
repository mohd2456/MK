/**
 * LibraryDestinations Component
 * ===============================
 * Configure where organized media ends up - Jellyfin and Plex library paths,
 * folder structure patterns, and scan-after-add settings.
 */

import {
  Film,
  Tv,
  Music,
  FolderTree,
  RefreshCw,
  Plus,
  MoreHorizontal,
  CheckCircle2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Toggle } from "@/components/ui/toggle";
import { DropdownMenu, DropdownItem, DropdownSeparator } from "@/components/ui/dropdown-menu";
import type { LibraryDestination, MediaCategory } from "@/types/drop-folders";

interface LibraryDestinationsProps {
  destinations?: LibraryDestination[];
  onToggleScan?: (id: string, enabled: boolean) => void;
  onAdd?: () => void;
}

const categoryIcon: Record<MediaCategory, typeof Film> = {
  movie: Film,
  tv_show: Tv,
  music: Music,
  unknown: FolderTree,
};

const serviceColors: Record<string, string> = {
  jellyfin: "bg-[#00a4dc]/10 text-[#00a4dc] border-[#00a4dc]/30",
  plex: "bg-[#e5a00d]/10 text-[#e5a00d] border-[#e5a00d]/30",
};

const defaultDestinations: LibraryDestination[] = [
  {
    id: "ld-1",
    name: "Jellyfin Movies",
    service: "jellyfin",
    media_type: "movie",
    base_path: "/mnt/media/movies",
    folder_pattern: "{title} ({year})",
    file_pattern: "{title} ({year})",
    enabled: true,
    scan_after_add: true,
  },
  {
    id: "ld-2",
    name: "Jellyfin TV Shows",
    service: "jellyfin",
    media_type: "tv_show",
    base_path: "/mnt/media/tv",
    folder_pattern: "{series_name}/Season {season:02d}",
    file_pattern: "S{season:02d}E{episode:02d} - {episode_title}",
    enabled: true,
    scan_after_add: true,
  },
  {
    id: "ld-3",
    name: "Jellyfin Music",
    service: "jellyfin",
    media_type: "music",
    base_path: "/mnt/media/music",
    folder_pattern: "{artist}/{album}",
    file_pattern: "{track:02d} - {title}",
    enabled: true,
    scan_after_add: true,
  },
  {
    id: "ld-4",
    name: "Plex Movies",
    service: "plex",
    media_type: "movie",
    base_path: "/mnt/plex/movies",
    folder_pattern: "{title} ({year})",
    file_pattern: "{title} ({year})",
    enabled: true,
    scan_after_add: true,
  },
  {
    id: "ld-5",
    name: "Plex TV Shows",
    service: "plex",
    media_type: "tv_show",
    base_path: "/mnt/plex/tv",
    folder_pattern: "{series_name}/Season {season:02d}",
    file_pattern: "{series_name} - S{season:02d}E{episode:02d} - {episode_title}",
    enabled: true,
    scan_after_add: false,
  },
  {
    id: "ld-6",
    name: "Plex Music",
    service: "plex",
    media_type: "music",
    base_path: "/mnt/plex/music",
    folder_pattern: "{artist}/{album}",
    file_pattern: "{track:02d} - {title}",
    enabled: false,
    scan_after_add: false,
  },
];

export function LibraryDestinations({
  destinations = defaultDestinations,
  onToggleScan,
  onAdd,
}: LibraryDestinationsProps) {
  // Group by service
  const jellyfinDests = destinations.filter((d) => d.service === "jellyfin");
  const plexDests = destinations.filter((d) => d.service === "plex");

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-mk-text-primary">Library Destinations</h3>
          <p className="text-xs text-mk-text-muted mt-0.5">
            Where organized media gets placed. MK creates proper folder structure for each service.
          </p>
        </div>
        <Button size="sm" onClick={onAdd}>
          <Plus size={14} />
          Add Destination
        </Button>
      </div>

      {/* Jellyfin Section */}
      <ServiceSection
        label="Jellyfin"
        service="jellyfin"
        destinations={jellyfinDests}
        onToggleScan={onToggleScan}
      />

      {/* Plex Section */}
      <ServiceSection
        label="Plex"
        service="plex"
        destinations={plexDests}
        onToggleScan={onToggleScan}
      />
    </div>
  );
}

function ServiceSection({
  label,
  service,
  destinations,
  onToggleScan,
}: {
  label: string;
  service: string;
  destinations: LibraryDestination[];
  onToggleScan?: (id: string, enabled: boolean) => void;
}) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <span
          className={cn(
            "px-2.5 py-0.5 rounded-full text-xs font-medium border",
            serviceColors[service]
          )}
        >
          {label}
        </span>
        <span className="text-xs text-mk-text-muted">
          {destinations.filter((d) => d.enabled).length}/{destinations.length} active
        </span>
      </div>

      <div className="space-y-2">
        {destinations.map((dest) => {
          const Icon = categoryIcon[dest.media_type];
          return (
            <div
              key={dest.id}
              className={cn(
                "rounded-[8px] border border-mk-border bg-mk-surface p-4",
                "hover:border-mk-border-strong transition-colors",
                !dest.enabled && "opacity-50"
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3 flex-1 min-w-0">
                  <Icon size={16} className="text-mk-text-secondary shrink-0 mt-0.5" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <h4 className="text-sm font-medium text-mk-text-primary">
                        {dest.name}
                      </h4>
                      {dest.enabled && (
                        <CheckCircle2 size={12} className="text-mk-success" />
                      )}
                    </div>
                    <p className="text-xs text-mk-text-muted font-mono mt-0.5">
                      {dest.base_path}
                    </p>

                    {/* Pattern preview */}
                    <div className="mt-2 space-y-1">
                      <div className="flex items-center gap-2 text-[11px]">
                        <span className="text-mk-text-muted">Folder:</span>
                        <code className="text-mk-accent bg-mk-accent/5 px-1.5 py-0.5 rounded font-mono">
                          {dest.folder_pattern}
                        </code>
                      </div>
                      <div className="flex items-center gap-2 text-[11px]">
                        <span className="text-mk-text-muted">File:</span>
                        <code className="text-mk-accent bg-mk-accent/5 px-1.5 py-0.5 rounded font-mono">
                          {dest.file_pattern}
                        </code>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Right: scan toggle + actions */}
                <div className="flex items-center gap-2 shrink-0">
                  <div className="flex items-center gap-1.5">
                    <RefreshCw size={11} className="text-mk-text-muted" />
                    <Toggle
                      checked={dest.scan_after_add}
                      onCheckedChange={(checked) => onToggleScan?.(dest.id, checked)}
                      label="Auto-scan"
                    />
                  </div>
                  <DropdownMenu
                    trigger={
                      <Button variant="ghost" size="icon-sm">
                        <MoreHorizontal size={14} />
                      </Button>
                    }
                  >
                    <DropdownItem>Edit Destination</DropdownItem>
                    <DropdownItem>Test Connection</DropdownItem>
                    <DropdownItem>Trigger Scan</DropdownItem>
                    <DropdownSeparator />
                    <DropdownItem destructive>Remove</DropdownItem>
                  </DropdownMenu>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
