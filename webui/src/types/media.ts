/**
 * MK OS Media Types
 * ==================
 * Disc ripper, library, and media management.
 */

export type DriveState = "empty" | "detecting" | "disc_detected" | "ripping" | "ejecting";
export type DiscType = "bluray" | "dvd" | "cd" | "uhd_bluray";
export type RipFormat = "mkv" | "mp4" | "iso";

export interface OpticalDrive {
  device: string;
  model: string;
  state: DriveState;
  disc_info?: DiscInfo;
}

export interface DiscInfo {
  title: string;
  year?: number;
  type: DiscType;
  titles_count: number;
  main_title_index: number;
  main_title_duration: string;
  main_title_size_bytes: number;
}

export interface RipProgress {
  active: boolean;
  drive: string;
  title: string;
  progress_percent: number;
  speed_mbps: number;
  eta_seconds: number;
  current_title: number;
  total_titles: number;
  output_path: string;
  format: RipFormat;
}

export interface RecentRip {
  id: string;
  title: string;
  date: string;
  size_bytes: number;
  format: RipFormat;
  duration_seconds: number;
  disc_type: DiscType;
}

export interface LibraryStats {
  movies_count: number;
  tv_shows_count: number;
  total_size_bytes: number;
  bluray_count: number;
  dvd_count: number;
  uhd_count: number;
}

export interface MediaSettings {
  auto_rip: boolean;
  output_path: string;
  default_format: RipFormat;
  min_length_minutes: number;
  notifications_enabled: boolean;
}
