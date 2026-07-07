/**
 * MediaPage — Disc ripper and library stats from real data
 */

import { RefreshCw, Disc3, Film, Tv, Music } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { useDiscStatus, useMediaLibrary } from "@/hooks/useApi";
import { formatBytes } from "@/lib/utils";

export function MediaPage() {
  const { data: discData, mutate: mdisc } = useDiscStatus();
  const { data: libData, mutate: mlib } = useMediaLibrary();

  const disc = discData as any;
  const lib = libData as any;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-mk-text-primary">Media</h1>
        <Button variant="secondary" size="sm" onClick={() => { mdisc(); mlib(); }}>
          <RefreshCw size={14} /> Refresh
        </Button>
      </div>

      <Tabs defaultValue="ripper">
        <TabsList>
          <TabsTrigger value="ripper">Disc Ripper</TabsTrigger>
          <TabsTrigger value="library">Library</TabsTrigger>
        </TabsList>

        {/* Disc Ripper — real detection */}
        <TabsContent value="ripper">
          <Card>
            <CardContent className="p-6 space-y-4">
              {!disc || !disc.drive_present ? (
                <div className="text-center py-8">
                  <Disc3 size={40} className="mx-auto mb-3 text-mk-text-muted opacity-40" />
                  <p className="text-mk-text-secondary">No optical drive detected</p>
                  <p className="text-xs text-mk-text-muted mt-1">
                    Connect a Blu-ray/DVD drive to enable disc ripping.
                  </p>
                </div>
              ) : (
                <>
                  <div className="flex items-center gap-3">
                    <Disc3 size={20} className="text-mk-accent" />
                    <span className="text-sm text-mk-text-primary">
                      {disc.drive?.vendor} {disc.drive?.model}
                    </span>
                    <span className="font-mono text-xs text-mk-text-muted">{disc.drive?.device}</span>
                  </div>
                  {disc.disc_inserted ? (
                    <div className="space-y-2">
                      <Badge variant="accent">DISC DETECTED</Badge>
                      {disc.disc_info && (
                        <p className="text-sm text-mk-text-secondary">
                          {disc.disc_info.title_count} titles found
                        </p>
                      )}
                      <Button className="mt-4"><Disc3 size={16} /> Rip Disc</Button>
                    </div>
                  ) : (
                    <p className="text-sm text-mk-text-muted">No disc inserted. Insert a disc to begin.</p>
                  )}
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Library stats — real filesystem counts */}
        <TabsContent value="library">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Card>
              <CardContent className="p-4 text-center">
                <Film size={20} className="mx-auto mb-2 text-mk-accent" />
                <p className="text-3xl font-bold text-mk-text-primary">{lib?.movies ?? 0}</p>
                <p className="text-sm text-mk-text-muted">Movies</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4 text-center">
                <Tv size={20} className="mx-auto mb-2 text-mk-accent" />
                <p className="text-3xl font-bold text-mk-text-primary">{lib?.tv_shows ?? 0}</p>
                <p className="text-sm text-mk-text-muted">TV Shows</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4 text-center">
                <Music size={20} className="mx-auto mb-2 text-mk-accent" />
                <p className="text-3xl font-bold text-mk-text-primary">{lib?.music_artists ?? 0}</p>
                <p className="text-sm text-mk-text-muted">Artists</p>
              </CardContent>
            </Card>
          </div>
          {lib?.total_size_bytes > 0 && (
            <Card className="mt-4">
              <CardContent className="p-4 text-center">
                <p className="text-lg font-bold text-mk-text-primary">{formatBytes(lib.total_size_bytes)}</p>
                <p className="text-sm text-mk-text-muted">Total Library Size</p>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
