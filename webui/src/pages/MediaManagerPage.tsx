/**
 * MediaManagerPage
 * =================
 * Full drop-folder media management system.
 * 
 * Concept: Users drop songs, movies, and TV shows into configured
 * folders. MK automatically:
 * 1. Identifies the media (TMDB, MusicBrainz, etc.)
 * 2. Organizes into proper folder structure
 * 3. Places files into Jellyfin and Plex library paths
 * 4. Optionally triggers library scan so content appears immediately
 *
 * Tabs:
 * - Drop Folders: Configured watch folders
 * - Queue: Real-time processing status
 * - Destinations: Jellyfin/Plex library paths and patterns
 * - Rules: File naming/structure rules with live examples
 * - History: Past processed items
 */

import { FolderInput, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { DropFolderStats } from "@/components/media-manager/DropFolderStats";
import { DropFolderList } from "@/components/media-manager/DropFolderList";
import { ProcessingQueue } from "@/components/media-manager/ProcessingQueue";
import { LibraryDestinations } from "@/components/media-manager/LibraryDestinations";
import { NamingRules } from "@/components/media-manager/NamingRules";
import { formatBytes, formatRelativeTime } from "@/lib/utils";

// Mock history data
const history = [
  { id: "h-1", title: "Oppenheimer (2023)", type: "movie", service: "jellyfin", destination: "/mnt/media/movies/Oppenheimer (2023)/", size: 58.2 * 1024 ** 3, processed_at: new Date(Date.now() - 3600000).toISOString() },
  { id: "h-2", title: "Breaking Bad S01E01 - Pilot", type: "tv_show", service: "jellyfin", destination: "/mnt/media/tv/Breaking Bad/Season 01/", size: 4.2 * 1024 ** 3, processed_at: new Date(Date.now() - 7200000).toISOString() },
  { id: "h-3", title: "Not Like Us - Kendrick Lamar", type: "music", service: "plex", destination: "/mnt/plex/music/Kendrick Lamar/GNX/", size: 42 * 1024 ** 2, processed_at: new Date(Date.now() - 10800000).toISOString() },
  { id: "h-4", title: "Dune: Part Two (2024)", type: "movie", service: "plex", destination: "/mnt/plex/movies/Dune Part Two (2024)/", size: 52 * 1024 ** 3, processed_at: new Date(Date.now() - 14400000).toISOString() },
  { id: "h-5", title: "The Bear S03E01 - Tomorrow", type: "tv_show", service: "jellyfin", destination: "/mnt/media/tv/The Bear/Season 03/", size: 3.1 * 1024 ** 3, processed_at: new Date(Date.now() - 18000000).toISOString() },
  { id: "h-6", title: "Luther - SZA", type: "music", service: "jellyfin", destination: "/mnt/media/music/SZA/SOS Deluxe/", size: 38 * 1024 ** 2, processed_at: new Date(Date.now() - 21600000).toISOString() },
  { id: "h-7", title: "Interstellar (2014)", type: "movie", service: "jellyfin", destination: "/mnt/media/movies/Interstellar (2014)/", size: 45 * 1024 ** 3, processed_at: new Date(Date.now() - 86400000).toISOString() },
  { id: "h-8", title: "Shogun S01E01 - Anjin", type: "tv_show", service: "plex", destination: "/mnt/plex/tv/Shogun/Season 01/", size: 5.4 * 1024 ** 3, processed_at: new Date(Date.now() - 90000000).toISOString() },
];

const typeBadge: Record<string, "info" | "accent" | "warning"> = {
  movie: "info",
  tv_show: "accent",
  music: "warning",
};

const typeLabel: Record<string, string> = {
  movie: "Movie",
  tv_show: "TV",
  music: "Music",
};

export function MediaManagerPage() {
  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-[8px] bg-mk-accent/10 border border-mk-accent/20 flex items-center justify-center">
            <FolderInput size={20} className="text-mk-accent" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-mk-text-primary">Media Manager</h1>
            <p className="text-sm text-mk-text-muted">
              Drop files &rarr; MK organizes &rarr; Jellyfin &amp; Plex ready
            </p>
          </div>
        </div>
        <Button variant="secondary" size="sm">
          <RefreshCw size={14} />
          Process All
        </Button>
      </div>

      {/* Stats overview */}
      <DropFolderStats />

      {/* Main tabbed content */}
      <Tabs defaultValue="queue">
        <TabsList>
          <TabsTrigger value="queue">Queue</TabsTrigger>
          <TabsTrigger value="folders">Drop Folders</TabsTrigger>
          <TabsTrigger value="destinations">Destinations</TabsTrigger>
          <TabsTrigger value="rules">Rules</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
        </TabsList>

        {/* Processing Queue */}
        <TabsContent value="queue">
          <ProcessingQueue />
        </TabsContent>

        {/* Drop Folders */}
        <TabsContent value="folders">
          <DropFolderList />
        </TabsContent>

        {/* Library Destinations */}
        <TabsContent value="destinations">
          <LibraryDestinations />
        </TabsContent>

        {/* Naming Rules */}
        <TabsContent value="rules">
          <NamingRules />
        </TabsContent>

        {/* History */}
        <TabsContent value="history">
          <div className="space-y-3">
            <div>
              <h3 className="text-sm font-semibold text-mk-text-primary">Processing History</h3>
              <p className="text-xs text-mk-text-muted mt-0.5">
                Recently organized media files.
              </p>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Title</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Service</TableHead>
                  <TableHead>Destination</TableHead>
                  <TableHead>Size</TableHead>
                  <TableHead>Processed</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {history.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell className="font-medium text-mk-text-primary">
                      {item.title}
                    </TableCell>
                    <TableCell>
                      <Badge variant={typeBadge[item.type]}>{typeLabel[item.type]}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={item.service === "jellyfin" ? "info" : "warning"}>
                        {item.service === "jellyfin" ? "Jellyfin" : "Plex"}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-[11px] text-mk-text-muted max-w-[250px] truncate">
                      {item.destination}
                    </TableCell>
                    <TableCell>{formatBytes(item.size)}</TableCell>
                    <TableCell className="text-mk-text-muted text-xs">
                      {formatRelativeTime(item.processed_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
