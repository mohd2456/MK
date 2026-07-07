/**
 * SnapshotList Component
 * =======================
 * Filterable list of ZFS snapshots with rollback/delete actions.
 */

import { formatBytes } from "@/lib/utils";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { RotateCcw, Trash2 } from "lucide-react";
import type { Snapshot } from "@/types/storage";

interface SnapshotListProps {
  snapshots?: Snapshot[];
}

const defaultSnapshots: Snapshot[] = [
  { name: "tank/media@auto-2024-01-15", dataset: "tank/media", size_bytes: 2.1 * 1024 ** 3, created: "2024-01-15T02:00:00Z", referenced_bytes: 28 * 1024 ** 4 },
  { name: "tank/media@auto-2024-01-14", dataset: "tank/media", size_bytes: 1.8 * 1024 ** 3, created: "2024-01-14T02:00:00Z", referenced_bytes: 27.8 * 1024 ** 4 },
  { name: "tank/apps@pre-update", dataset: "tank/apps", size_bytes: 500 * 1024 ** 2, created: "2024-01-15T14:00:00Z", referenced_bytes: 4 * 1024 ** 4 },
];

export function SnapshotList({ snapshots = defaultSnapshots }: SnapshotListProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Dataset</TableHead>
          <TableHead>Size</TableHead>
          <TableHead>Created</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {snapshots.map((snap) => (
          <TableRow key={snap.name}>
            <TableCell className="font-mono text-xs text-mk-text-primary">
              {snap.name}
            </TableCell>
            <TableCell>{snap.dataset}</TableCell>
            <TableCell>{formatBytes(snap.size_bytes)}</TableCell>
            <TableCell>
              {new Date(snap.created).toLocaleDateString()}
            </TableCell>
            <TableCell className="text-right">
              <div className="flex items-center gap-1 justify-end">
                <Button variant="ghost" size="icon-sm" aria-label="Rollback">
                  <RotateCcw size={13} />
                </Button>
                <Button variant="ghost" size="icon-sm" aria-label="Delete">
                  <Trash2 size={13} className="text-mk-error" />
                </Button>
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
