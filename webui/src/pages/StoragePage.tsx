/**
 * StoragePage — Real ZFS/disk data from backend
 */

import { RefreshCw, HardDrive, Database, Camera } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import { useStoragePools, useStorageDatasets, useStorageDisks, useStorageSnapshots } from "@/hooks/useApi";

export function StoragePage() {
  const { data: poolsData, mutate: mp } = useStoragePools();
  const { data: datasetsData, mutate: md } = useStorageDatasets();
  const { data: disksData, mutate: mdi } = useStorageDisks();
  const { data: snapsData, mutate: ms } = useStorageSnapshots();

  const pools = (poolsData as any)?.pools ?? [];
  const datasets = (datasetsData as any)?.datasets ?? [];
  const disks = (disksData as any)?.disks ?? [];
  const snapshots = (snapsData as any)?.snapshots ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-mk-text-primary">Storage</h1>
        <Button variant="secondary" size="sm" onClick={() => { mp(); md(); mdi(); ms(); }}>
          <RefreshCw size={14} /> Refresh
        </Button>
      </div>

      <Tabs defaultValue="pools">
        <TabsList>
          <TabsTrigger value="pools">Pools</TabsTrigger>
          <TabsTrigger value="datasets">Datasets</TabsTrigger>
          <TabsTrigger value="disks">Disks</TabsTrigger>
          <TabsTrigger value="snapshots">Snapshots</TabsTrigger>
        </TabsList>

        <TabsContent value="pools">
          {pools.length === 0 ? (
            <Card><CardContent className="p-6 text-center text-mk-text-muted">
              <Database size={32} className="mx-auto mb-2 opacity-40" />
              <p>No ZFS pools detected.</p>
              <p className="text-xs mt-1">ZFS is not configured or zpool is not available.</p>
            </CardContent></Card>
          ) : (
            <Table>
              <TableHeader><TableRow>
                <TableHead>Pool</TableHead><TableHead>Size</TableHead>
                <TableHead>Used</TableHead><TableHead>Free</TableHead>
                <TableHead>Frag</TableHead><TableHead>Health</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {pools.map((p: any) => (
                  <TableRow key={p.name}>
                    <TableCell className="font-medium text-mk-text-primary">{p.name}</TableCell>
                    <TableCell>{p.size}</TableCell>
                    <TableCell>{p.allocated}</TableCell>
                    <TableCell>{p.free}</TableCell>
                    <TableCell>{p.fragmentation}</TableCell>
                    <TableCell>
                      <Badge variant={p.health === "ONLINE" ? "success" : "error"}>{p.health}</Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </TabsContent>

        <TabsContent value="datasets">
          {datasets.length === 0 ? (
            <Card><CardContent className="p-6 text-center text-mk-text-muted">
              No ZFS datasets found.
            </CardContent></Card>
          ) : (
            <Table>
              <TableHeader><TableRow>
                <TableHead>Dataset</TableHead><TableHead>Used</TableHead>
                <TableHead>Available</TableHead><TableHead>Mountpoint</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {datasets.map((d: any) => (
                  <TableRow key={d.name}>
                    <TableCell className="font-mono text-xs text-mk-text-primary">{d.name}</TableCell>
                    <TableCell>{d.used}</TableCell>
                    <TableCell>{d.available}</TableCell>
                    <TableCell className="font-mono text-xs text-mk-text-muted">{d.mountpoint}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </TabsContent>

        <TabsContent value="disks">
          {disks.length === 0 ? (
            <Card><CardContent className="p-6 text-center text-mk-text-muted">
              <HardDrive size={32} className="mx-auto mb-2 opacity-40" />
              <p>No disk information available.</p>
            </CardContent></Card>
          ) : (
            <Table>
              <TableHeader><TableRow>
                <TableHead>Device</TableHead><TableHead>Model</TableHead>
                <TableHead>Size</TableHead><TableHead>Type</TableHead>
                <TableHead>Temp</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {disks.map((d: any) => (
                  <TableRow key={d.name}>
                    <TableCell className="font-mono">/dev/{d.name}</TableCell>
                    <TableCell className="text-mk-text-primary">{d.model || "—"}</TableCell>
                    <TableCell>{d.size}</TableCell>
                    <TableCell>{d.rotational ? "HDD" : "SSD/NVMe"}</TableCell>
                    <TableCell>{d.temperature ? `${d.temperature}C` : "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </TabsContent>

        <TabsContent value="snapshots">
          {snapshots.length === 0 ? (
            <Card><CardContent className="p-6 text-center text-mk-text-muted">
              <Camera size={32} className="mx-auto mb-2 opacity-40" />
              <p>No snapshots found.</p>
            </CardContent></Card>
          ) : (
            <Table>
              <TableHeader><TableRow>
                <TableHead>Snapshot</TableHead><TableHead>Used</TableHead><TableHead>Created</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {snapshots.map((s: any) => (
                  <TableRow key={s.name}>
                    <TableCell className="font-mono text-xs text-mk-text-primary">{s.name}</TableCell>
                    <TableCell>{s.used}</TableCell>
                    <TableCell className="text-mk-text-muted">{s.creation}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
