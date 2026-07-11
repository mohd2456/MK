/**
 * LibraryStats Component
 * =======================
 * Displays media library statistics in summary cards.
 */

import { Card, CardContent } from "@/components/ui/card";
import { formatBytes } from "@/lib/utils";
import type { LibraryStats as LibraryStatsType } from "@/types/media";

interface LibraryStatsProps {
  stats: LibraryStatsType;
}

export function LibraryStats({ stats }: LibraryStatsProps) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-3xl font-bold text-mk-text-primary">
              {stats.movies_count}
            </p>
            <p className="text-sm text-mk-text-muted">Movies</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-3xl font-bold text-mk-text-primary">
              {stats.tv_shows_count}
            </p>
            <p className="text-sm text-mk-text-muted">TV Shows</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-3xl font-bold text-mk-text-primary">
              {formatBytes(stats.total_size_bytes)}
            </p>
            <p className="text-sm text-mk-text-muted">Total Size</p>
          </CardContent>
        </Card>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-2xl font-bold text-mk-accent">
              {stats.bluray_count}
            </p>
            <p className="text-xs text-mk-text-muted">Blu-rays</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-2xl font-bold text-mk-text-primary">
              {stats.dvd_count}
            </p>
            <p className="text-xs text-mk-text-muted">DVDs</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-2xl font-bold text-mk-warning">
              {stats.uhd_count}
            </p>
            <p className="text-xs text-mk-text-muted">4K UHD</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
