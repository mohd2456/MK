/**
 * StoragePage
 * ============
 * Pool management, datasets, snapshots, disks, and shares.
 * Tabbed interface with all storage operations on one page.
 */

import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { PoolCard } from "@/components/storage/PoolCard";
import { DatasetTable } from "@/components/storage/DatasetTable";
import { SnapshotList } from "@/components/storage/SnapshotList";
import { DiskGrid } from "@/components/storage/DiskGrid";
import { ShareManager } from "@/components/storage/ShareManager";
import type { Pool } from "@/types/storage";

const mockPools: Pool[] = [
  { name: "tank", layout: "RAIDZ2", size_bytes: 48 * 1024 ** 4, used_bytes: 36 * 1024 ** 4, usage_percent: 75, health: "ONLINE", disk_count: 6, scrub_last: "2024-01-14", scrub_errors: 0 },
  { name: "fast", layout: "Mirror", size_bytes: 2 * 1024 ** 4, used_bytes: 0.8 * 1024 ** 4, usage_percent: 40, health: "ONLINE", disk_count: 2, scrub_last: "2024-01-15", scrub_errors: 0 },
  { name: "backup", layout: "RAIDZ1", size_bytes: 24 * 1024 ** 4, used_bytes: 20 * 1024 ** 4, usage_percent: 83, health: "DEGRADED", disk_count: 4, scrub_last: "2024-01-07", scrub_errors: 0 },
];

export function StoragePage() {
  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-mk-text-primary">Storage</h1>
        <Button size="sm">
          <Plus size={14} />
          Create Pool
        </Button>
      </div>

      {/* Tabbed content */}
      <Tabs defaultValue="pools">
        <TabsList>
          <TabsTrigger value="pools">Pools</TabsTrigger>
          <TabsTrigger value="datasets">Datasets</TabsTrigger>
          <TabsTrigger value="snapshots">Snapshots</TabsTrigger>
          <TabsTrigger value="disks">Disks</TabsTrigger>
          <TabsTrigger value="shares">Shares</TabsTrigger>
        </TabsList>

        <TabsContent value="pools">
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {mockPools.map((pool) => (
              <PoolCard key={pool.name} pool={pool} />
            ))}
          </div>
        </TabsContent>

        <TabsContent value="datasets">
          <DatasetTable />
        </TabsContent>

        <TabsContent value="snapshots">
          <SnapshotList />
        </TabsContent>

        <TabsContent value="disks">
          <DiskGrid />
        </TabsContent>

        <TabsContent value="shares">
          <ShareManager />
        </TabsContent>
      </Tabs>
    </div>
  );
}
