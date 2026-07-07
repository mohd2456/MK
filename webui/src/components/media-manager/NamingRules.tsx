/**
 * NamingRules Component
 * ======================
 * Shows how MK structures files for each media type.
 * Visual preview with example inputs -> outputs so the user
 * knows exactly what folder structure they'll get.
 */

import { Film, Tv, Music, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { NamingRule, MediaCategory } from "@/types/drop-folders";

interface NamingRulesProps {
  rules?: NamingRule[];
}

const categoryIcon: Record<MediaCategory, typeof Film> = {
  movie: Film,
  tv_show: Tv,
  music: Music,
  unknown: Film,
};

const categoryLabel: Record<MediaCategory, string> = {
  movie: "Movies",
  tv_show: "TV Shows",
  music: "Music",
  unknown: "Other",
};

const defaultRules: NamingRule[] = [
  {
    media_type: "movie",
    folder_structure: "/movies/{title} ({year})/",
    file_naming: "{title} ({year}).{ext}",
    example_input: "Oppenheimer.2023.2160p.UHD.BluRay.x265.mkv",
    example_output: "/movies/Oppenheimer (2023)/Oppenheimer (2023).mkv",
  },
  {
    media_type: "tv_show",
    folder_structure: "/tv/{series}/Season {season:02d}/",
    file_naming: "S{season:02d}E{episode:02d} - {episode_title}.{ext}",
    example_input: "Breaking.Bad.S01E01.720p.BluRay.mkv",
    example_output: "/tv/Breaking Bad/Season 01/S01E01 - Pilot.mkv",
  },
  {
    media_type: "music",
    folder_structure: "/music/{artist}/{album}/",
    file_naming: "{track:02d} - {title}.{ext}",
    example_input: "Kendrick Lamar - Not Like Us.flac",
    example_output: "/music/Kendrick Lamar/GNX/01 - Not Like Us.flac",
  },
];

export function NamingRules({ rules = defaultRules }: NamingRulesProps) {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-mk-text-primary">File Structure Rules</h3>
        <p className="text-xs text-mk-text-muted mt-0.5">
          How MK organizes your drops. These patterns are used for both Jellyfin and Plex.
        </p>
      </div>

      <div className="space-y-4">
        {rules.map((rule) => {
          const Icon = categoryIcon[rule.media_type];
          return (
            <div
              key={rule.media_type}
              className={cn(
                "rounded-[8px] border border-mk-border bg-mk-surface p-4"
              )}
            >
              {/* Header */}
              <div className="flex items-center gap-2 mb-3">
                <Icon size={14} className="text-mk-accent" />
                <h4 className="text-sm font-medium text-mk-text-primary">
                  {categoryLabel[rule.media_type]}
                </h4>
              </div>

              {/* Patterns */}
              <div className="space-y-2 mb-3">
                <div className="flex items-start gap-2 text-xs">
                  <span className="text-mk-text-muted min-w-[60px] shrink-0 pt-0.5">Folder:</span>
                  <code className="text-mk-accent bg-mk-elevated px-2 py-1 rounded font-mono break-all">
                    {rule.folder_structure}
                  </code>
                </div>
                <div className="flex items-start gap-2 text-xs">
                  <span className="text-mk-text-muted min-w-[60px] shrink-0 pt-0.5">File:</span>
                  <code className="text-mk-accent bg-mk-elevated px-2 py-1 rounded font-mono break-all">
                    {rule.file_naming}
                  </code>
                </div>
              </div>

              {/* Example transformation */}
              <div className="border-t border-mk-border pt-3">
                <p className="text-[10px] text-mk-text-muted uppercase tracking-wider font-medium mb-2">
                  Example
                </p>
                <div className="flex items-start gap-2">
                  {/* Input */}
                  <div className="flex-1 min-w-0">
                    <p className="text-[10px] text-mk-text-muted mb-0.5">Input (dropped file)</p>
                    <code className="text-[11px] text-mk-error/80 bg-mk-error/5 px-2 py-1 rounded font-mono block truncate">
                      {rule.example_input}
                    </code>
                  </div>

                  {/* Arrow */}
                  <ArrowRight size={14} className="text-mk-accent shrink-0 mt-4" />

                  {/* Output */}
                  <div className="flex-1 min-w-0">
                    <p className="text-[10px] text-mk-text-muted mb-0.5">Output (organized)</p>
                    <code className="text-[11px] text-mk-success/80 bg-mk-success/5 px-2 py-1 rounded font-mono block truncate">
                      {rule.example_output}
                    </code>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
