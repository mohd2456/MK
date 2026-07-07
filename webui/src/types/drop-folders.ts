/**
 * MK OS Drop Folders Types
 * =========================
 * Media drop folder management - files dropped here are automatically
 * identified, organized into proper folder structure, and linked to
 * Jellyfin/Plex libraries.
 */

/** Media type detected by MK */
export type MediaCategory = "movie" | "tv_show" | "music" | "unknown";

/** Processing status for a dropped item */
export type ProcessingStatus =
  | "pending"       // Waiting in queue
  | "identifying"   // MK is looking up metadata
  | "organizing"    // Moving/renaming to proper structure
  | "complete"      // Done, available in Jellyfin/Plex
  | "failed"        // Something went wrong
  | "manual_review"; // MK couldn't determine, needs user input

/** A configured drop folder */
export interface DropFolder {
  id: string;
  name: string;
  path: string;
  media_type: MediaCategory | "auto"; // "auto" = MK figures it out
  enabled: boolean;
  watch_enabled: boolean; // inotify-style watch for new files
  items_pending: number;
  last_activity: string;
}

/** An item that was dropped and is being processed */
export interface DropItem {
  id: string;
  filename: string;
  original_path: string;
  size_bytes: number;
  detected_type: MediaCategory;
  status: ProcessingStatus;
  progress_percent: number;
  dropped_at: string;
  processed_at?: string;

  // Metadata detected by MK
  metadata?: DropItemMetadata;

  // Where it ended up
  destination_path?: string;
  error_message?: string;
}

/** Metadata identified for a drop item */
export interface DropItemMetadata {
  title: string;
  year?: number;
  // Movies
  tmdb_id?: number;
  // TV Shows
  series_name?: string;
  season?: number;
  episode?: number;
  episode_title?: string;
  // Music
  artist?: string;
  album?: string;
  track_number?: number;
  genre?: string;
}

/** Library destination configuration for Jellyfin/Plex */
export interface LibraryDestination {
  id: string;
  name: string;
  service: "jellyfin" | "plex";
  media_type: MediaCategory;
  base_path: string;
  folder_pattern: string; // e.g., "{title} ({year})" or "{artist}/{album}"
  file_pattern: string;   // e.g., "{title} ({year})" or "S{season:02d}E{episode:02d} - {episode_title}"
  enabled: boolean;
  scan_after_add: boolean; // Trigger library scan after file is placed
}

/** Naming rule configuration */
export interface NamingRule {
  media_type: MediaCategory;
  folder_structure: string;
  file_naming: string;
  example_input: string;
  example_output: string;
}

/** Overall drop folder stats */
export interface DropFolderStats {
  total_processed: number;
  processed_today: number;
  pending_count: number;
  failed_count: number;
  manual_review_count: number;
  total_size_processed_bytes: number;
}
