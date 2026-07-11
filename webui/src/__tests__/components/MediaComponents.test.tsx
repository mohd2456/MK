/**
 * Media Components Tests
 * =======================
 * Tests for media-domain components: DriveStatus, RipProgress, RecentRips, LibraryStats, AutoRipToggle.
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@/test/utils";
import { DriveStatus } from "@/components/media/DriveStatus";
import { RipProgress } from "@/components/media/RipProgress";
import { RecentRips } from "@/components/media/RecentRips";
import { LibraryStats } from "@/components/media/LibraryStats";
import { AutoRipToggle } from "@/components/media/AutoRipToggle";
import type { OpticalDrive, RipProgress as RipProgressType, RecentRip, LibraryStats as LibraryStatsType, MediaSettings } from "@/types/media";

const mockDrive: OpticalDrive = {
  device: "/dev/sr0",
  model: "Pioneer BDR-XD07",
  state: "disc_detected",
  disc_info: {
    title: "Inception",
    year: 2010,
    type: "bluray",
    titles_count: 30,
    main_title_index: 1,
    main_title_duration: "2h 28m",
    main_title_size_bytes: 32 * 1024 ** 3,
  },
};

const mockRipActive: RipProgressType = {
  active: true,
  drive: "/dev/sr0",
  title: "Inception (2010)",
  progress_percent: 60,
  speed_mbps: 95,
  eta_seconds: 900,
  current_title: 1,
  total_titles: 1,
  output_path: "/mnt/media/movies/Inception/",
  format: "mkv",
};

const mockRipInactive: RipProgressType = {
  active: false,
  drive: "/dev/sr0",
  title: "",
  progress_percent: 0,
  speed_mbps: 0,
  eta_seconds: 0,
  current_title: 0,
  total_titles: 0,
  output_path: "",
  format: "mkv",
};

const mockRips: RecentRip[] = [
  { id: "1", title: "Inception (2010)", date: "2024-02-10", size_bytes: 32 * 1024 ** 3, format: "mkv", duration_seconds: 3600, disc_type: "bluray" },
  { id: "2", title: "Interstellar (2014)", date: "2024-02-09", size_bytes: 40 * 1024 ** 3, format: "mkv", duration_seconds: 4200, disc_type: "bluray" },
];

const mockStats: LibraryStatsType = {
  movies_count: 500,
  tv_shows_count: 80,
  total_size_bytes: 10 * 1024 ** 4,
  bluray_count: 300,
  dvd_count: 200,
  uhd_count: 50,
};

const mockSettings: MediaSettings = {
  auto_rip: true,
  output_path: "/mnt/media/rips/",
  default_format: "mkv",
  min_length_minutes: 30,
  notifications_enabled: true,
};

describe("DriveStatus", () => {
  it("renders drive device and model", () => {
    render(<DriveStatus drive={mockDrive} />);
    expect(screen.getByText(/\/dev\/sr0/)).toBeInTheDocument();
    expect(screen.getByText(/Pioneer BDR-XD07/)).toBeInTheDocument();
  });

  it("displays disc detected badge", () => {
    render(<DriveStatus drive={mockDrive} />);
    expect(screen.getByText("DISC DETECTED")).toBeInTheDocument();
  });

  it("shows disc info when available", () => {
    render(<DriveStatus drive={mockDrive} />);
    expect(screen.getByText(/Inception/)).toBeInTheDocument();
    expect(screen.getByText(/bluray/)).toBeInTheDocument();
    expect(screen.getByText("30")).toBeInTheDocument();
  });

  it("shows NO DISC when drive is empty", () => {
    const emptyDrive: OpticalDrive = {
      device: "/dev/sr0",
      model: "Generic Drive",
      state: "empty",
    };
    render(<DriveStatus drive={emptyDrive} />);
    expect(screen.getByText("NO DISC")).toBeInTheDocument();
  });
});

describe("RipProgress", () => {
  it("shows progress when active", () => {
    render(<RipProgress progress={mockRipActive} />);
    expect(screen.getByText("Inception (2010)")).toBeInTheDocument();
    expect(screen.getByText(/95 MB\/s/)).toBeInTheDocument();
  });

  it("shows no rip message when inactive", () => {
    render(<RipProgress progress={mockRipInactive} />);
    expect(screen.getByText("No rip in progress.")).toBeInTheDocument();
  });
});

describe("RecentRips", () => {
  it("renders rip history table", () => {
    render(<RecentRips rips={mockRips} />);
    expect(screen.getByText("Inception (2010)")).toBeInTheDocument();
    expect(screen.getByText("Interstellar (2014)")).toBeInTheDocument();
  });

  it("shows empty message when no rips", () => {
    render(<RecentRips rips={[]} />);
    expect(screen.getByText("No recent rips found.")).toBeInTheDocument();
  });
});

describe("LibraryStats", () => {
  it("renders movie and TV show counts", () => {
    render(<LibraryStats stats={mockStats} />);
    expect(screen.getByText("500")).toBeInTheDocument();
    expect(screen.getByText("80")).toBeInTheDocument();
    expect(screen.getByText("Movies")).toBeInTheDocument();
    expect(screen.getByText("TV Shows")).toBeInTheDocument();
  });

  it("renders disc type breakdown", () => {
    render(<LibraryStats stats={mockStats} />);
    expect(screen.getByText("300")).toBeInTheDocument();
    expect(screen.getByText("200")).toBeInTheDocument();
    expect(screen.getByText("50")).toBeInTheDocument();
    expect(screen.getByText("Blu-rays")).toBeInTheDocument();
    expect(screen.getByText("DVDs")).toBeInTheDocument();
    expect(screen.getByText("4K UHD")).toBeInTheDocument();
  });
});

describe("AutoRipToggle", () => {
  it("renders settings values", () => {
    render(<AutoRipToggle settings={mockSettings} />);
    expect(screen.getByText("Auto-rip")).toBeInTheDocument();
    expect(screen.getByText("/mnt/media/rips/")).toBeInTheDocument();
    expect(screen.getByText("MKV (passthrough)")).toBeInTheDocument();
    expect(screen.getByText("30 min")).toBeInTheDocument();
    expect(screen.getByText("ON")).toBeInTheDocument();
  });

  it("shows OFF badge when notifications disabled", () => {
    const settings: MediaSettings = { ...mockSettings, notifications_enabled: false };
    render(<AutoRipToggle settings={settings} />);
    expect(screen.getByText("OFF")).toBeInTheDocument();
  });
});
