/**
 * MediaPage
 * ==========
 * Disc ripper control, library management, and recent rips.
 */

import { RefreshCw, Disc3, CircleArrowUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Toggle } from "@/components/ui/toggle";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Card, CardContent } from "@/components/ui/card";
import { cn, formatBytes } from "@/lib/utils";
import { useState } from "react";

export function MediaPage() {
  const [autoRip, setAutoRip] = useState(true);

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
          <Card>
            <CardContent className="p-6 space-y-6">
              {/* Drive info */}
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Disc3 size={18} className="text-mk-accent" />
                  <span className="text-sm text-mk-text-secondary">
                    Drive: <span className="text-mk-text-primary font-mono">/dev/sr0</span> (Pioneer BDR-XD07)
                  </span>
                </div>
                <Badge variant="accent">DISC DETECTED</Badge>
              </div>

              {/* Disc info card */}
              <div className={cn(
                "rounded-[8px] border border-mk-border bg-mk-elevated p-4 space-y-2"
              )}>
                <div className="grid grid-cols-2 gap-y-1.5 text-sm">
                  <span className="text-mk-text-muted">Title:</span>
                  <span className="text-mk-text-primary font-medium">The Matrix (1999)</span>
                  <span className="text-mk-text-muted">Type:</span>
                  <span className="text-mk-text-primary">Blu-ray</span>
                  <span className="text-mk-text-muted">Titles found:</span>
                  <span className="text-mk-text-primary">42</span>
                  <span className="text-mk-text-muted">Main feature:</span>
                  <span className="text-mk-text-primary">Title 1 (2h 16m, 28.4 GB)</span>
                  <span className="text-mk-text-muted">Output:</span>
                  <span className="text-mk-text-primary font-mono text-xs">/mnt/media/movies/The Matrix (1999)/</span>
                  <span className="text-mk-text-muted">Format:</span>
                  <span className="text-mk-text-primary">MKV (passthrough)</span>
                </div>
              </div>

              {/* Progress */}
              <div className="space-y-2">
                <Progress value={45} variant="accent" size="lg" showLabel />
                <p className="text-xs text-mk-text-muted">
                  Ripping title 1/1... ETA 25 min (112 MB/s)
                </p>
              </div>

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
        </TabsContent>

        {/* Library */}
        <TabsContent value="library">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Card>
              <CardContent className="p-4 text-center">
                <p className="text-3xl font-bold text-mk-text-primary">847</p>
                <p className="text-sm text-mk-text-muted">Movies</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4 text-center">
                <p className="text-3xl font-bold text-mk-text-primary">124</p>
                <p className="text-sm text-mk-text-muted">TV Shows</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4 text-center">
                <p className="text-3xl font-bold text-mk-text-primary">18.4 TB</p>
                <p className="text-sm text-mk-text-muted">Total Size</p>
              </CardContent>
            </Card>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-4">
            <Card>
              <CardContent className="p-4 text-center">
                <p className="text-2xl font-bold text-mk-accent">412</p>
                <p className="text-xs text-mk-text-muted">Blu-rays</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4 text-center">
                <p className="text-2xl font-bold text-mk-text-primary">435</p>
                <p className="text-xs text-mk-text-muted">DVDs</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4 text-center">
                <p className="text-2xl font-bold text-mk-warning">89</p>
                <p className="text-xs text-mk-text-muted">4K UHD</p>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Recent Rips */}
        <TabsContent value="recent">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Title</TableHead>
                <TableHead>Date</TableHead>
                <TableHead>Size</TableHead>
                <TableHead>Format</TableHead>
                <TableHead>Duration</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell className="font-medium text-mk-text-primary">The Matrix (1999)</TableCell>
                <TableCell>2024-01-15</TableCell>
                <TableCell>{formatBytes(28 * 1024 ** 3)}</TableCell>
                <TableCell><Badge>MKV</Badge></TableCell>
                <TableCell>52m</TableCell>
              </TableRow>
              <TableRow>
                <TableCell className="font-medium text-mk-text-primary">Blade Runner 2049</TableCell>
                <TableCell>2024-01-14</TableCell>
                <TableCell>{formatBytes(45 * 1024 ** 3)}</TableCell>
                <TableCell><Badge>MKV</Badge></TableCell>
                <TableCell>1h 8m</TableCell>
              </TableRow>
              <TableRow>
                <TableCell className="font-medium text-mk-text-primary">Dune Part Two</TableCell>
                <TableCell>2024-01-13</TableCell>
                <TableCell>{formatBytes(52 * 1024 ** 3)}</TableCell>
                <TableCell><Badge>MKV</Badge></TableCell>
                <TableCell>1h 22m</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </TabsContent>

        {/* Settings */}
        <TabsContent value="settings">
          <div className={cn(
            "rounded-[8px] border border-mk-border bg-mk-surface p-6 space-y-4",
            "max-w-lg"
          )}>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-mk-text-primary">Auto-rip</p>
                <p className="text-xs text-mk-text-muted">Automatically rip when disc inserted</p>
              </div>
              <Toggle checked={autoRip} onCheckedChange={setAutoRip} />
            </div>
            <div className="border-t border-mk-border pt-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-mk-text-secondary">Output path</span>
                <span className="text-sm font-mono text-mk-text-primary">/mnt/media/rips/</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-mk-text-secondary">Default format</span>
                <span className="text-sm text-mk-text-primary">MKV (passthrough)</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-mk-text-secondary">Min length</span>
                <span className="text-sm text-mk-text-primary">30 min</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-mk-text-secondary">Notifications</span>
                <Badge variant="success">ON</Badge>
              </div>
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
