/**
 * MediaPage
 * ==========
 * Disc ripper control, library management, and recent rips.
 * Uses dedicated media components with API data and mock fallbacks.
 */

import { RefreshCw, Disc3, CircleArrowUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import { useMediaDrives, useMediaRipStatus } from "@/hooks/useApi";
import { DriveStatus } from "@/components/media/DriveStatus";
import { RipProgress } from "@/components/media/RipProgress";
import { RecentRips } from "@/components/media/RecentRips";
import { LibraryStats } from "@/components/media/LibraryStats";
import { AutoRipToggle } from "@/components/media/AutoRipToggle";
import { LoadingState } from "@/components/LoadingState";
import type { OpticalDrive, RipProgress as RipProgressType, RecentRip, LibraryStats as LibraryStatsType, MediaSettings } from "@/types/media";

// ─── Fallback Mock Data ───

const mockDrive: OpticalDrive = {
  device: "/dev/sr0",
  model: "Pioneer BDR-XD07",
  state: "disc_detected",
  disc_info: {
    title: "The Matrix",
    year: 1999,
    type: "bluray",
    titles_count: 42,
    main_title_index: 1,
    main_title_duration: "2h 16m",
    main_title_size_bytes: 28.4 * 1024 ** 3,
  },
};

const mockRipProgress: RipProgressType = {
  active: true,
  drive: "/dev/sr0",
  title: "The Matrix (1999)",
  progress_percent: 45,
  speed_mbps: 112,
  eta_seconds: 25 * 60,
  current_title: 1,
  total_titles: 1,
  output_path: "/mnt/media/movies/The Matrix (1999)/",
  format: "mkv",
};

const mockRecentRips: RecentRip[] = [
  { id: "1", title: "The Matrix (1999)", date: "2024-01-15", size_bytes: 28 * 1024 ** 3, format: "mkv", duration_seconds: 52 * 60, disc_type: "bluray" },
  { id: "2", title: "Blade Runner 2049", date: "2024-01-14", size_bytes: 45 * 1024 ** 3, format: "mkv", duration_seconds: 68 * 60, disc_type: "bluray" },
  { id: "3", title: "Dune Part Two", date: "2024-01-13", size_bytes: 52 * 1024 ** 3, format: "mkv", duration_seconds: 82 * 60, disc_type: "bluray" },
];

const mockLibraryStats: LibraryStatsType = {
  movies_count: 847,
  tv_shows_count: 124,
  total_size_bytes: 18.4 * 1024 ** 4,
  bluray_count: 412,
  dvd_count: 435,
  uhd_count: 89,
};

const mockSettings: MediaSettings = {
  auto_rip: true,
  output_path: "/mnt/media/rips/",
  default_format: "mkv",
  min_length_minutes: 30,
  notifications_enabled: true,
};

export function MediaPage() {
  const { data: drivesData, isLoading: drivesLoading } = useMediaDrives();
  const { data: ripData, isLoading: ripLoading } = useMediaRipStatus();

  // Build drive object from API or fallback
  const drive: OpticalDrive = drivesData?.[0]
    ? { device: drivesData[0].device, model: drivesData[0].label || drivesData[0].type, state: (drivesData[0].status as OpticalDrive["state"]) || "empty" }
    : mockDrive;

  const ripProgress: RipProgressType = ripData?.active
    ? {
        active: true,
        drive: ripData.device ?? "/dev/sr0",
        title: ripData.title ?? "Unknown",
        progress_percent: ripData.progress ?? 0,
        speed_mbps: 0,
        eta_seconds: 0,
        current_title: 1,
        total_titles: 1,
        output_path: "",
        format: "mkv",
      }
    : mockRipProgress;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-mk-text-primary">Media</h1>
        <Button variant="secondary" size="sm">
          <RefreshCw size={14} />
          Scan Drives
        </Button>
      </div>

      <Tabs defaultValue="ripper">
        <TabsList>
          <TabsTrigger value="ripper">Disc Ripper</TabsTrigger>
          <TabsTrigger value="library">Library</TabsTrigger>
          <TabsTrigger value="recent">Recent Rips</TabsTrigger>
          <TabsTrigger value="settings">Settings</TabsTrigger>
        </TabsList>

        {/* Disc Ripper */}
        <TabsContent value="ripper">
          {drivesLoading ? (
            <LoadingState variant="card" rows={1} />
          ) : (
            <Card>
              <CardContent className="p-6 space-y-6">
                <DriveStatus drive={drive} />

                <RipProgress progress={ripProgress} />

                {/* Actions */}
                <div className="flex items-center gap-3">
                  <Button size="lg" className="flex-1">
                    <Disc3 size={16} />
                    Rip Disc
                  </Button>
                  <Button variant="secondary" size="lg">
                    <CircleArrowUp size={16} />
                    Eject
                  </Button>
                  <Button variant="destructive" size="lg">
                    Cancel
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Library */}
        <TabsContent value="library">
          <LibraryStats stats={mockLibraryStats} />
        </TabsContent>

        {/* Recent Rips */}
        <TabsContent value="recent">
          {ripLoading ? (
            <LoadingState variant="table" rows={3} />
          ) : (
            <RecentRips rips={mockRecentRips} />
          )}
        </TabsContent>

        {/* Settings */}
        <TabsContent value="settings">
          <AutoRipToggle settings={mockSettings} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
