/**
 * DatasetTable Component
 * =======================
 * Sortable table of ZFS datasets with key properties.
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
import type { Dataset } from "@/types/storage";

interface DatasetTableProps {
  datasets?: Dataset[];
}

const defaultDatasets: Dataset[] = [
  {
    name: "tank/media",
    pool: "tank",
    used_bytes: 28 * 1024 ** 4,
    available_bytes: 12 * 1024 ** 4,
    compression: "lz4",
    mountpoint: "/mnt/media",
    record_size: "1M",
    quota: null,
  },
  {
    name: "tank/apps",
    pool: "tank",
    used_bytes: 4 * 1024 ** 4,
    available_bytes: 12 * 1024 ** 4,
    compression: "zstd",
    mountpoint: "/mnt/apps",
    record_size: "128K",
    quota: null,
  },
  {
    name: "tank/backups",
    pool: "tank",
    used_bytes: 3.5 * 1024 ** 4,
    available_bytes: 12 * 1024 ** 4,
    compression: "off",
    mountpoint: "/mnt/backups",
    record_size: "1M",
    quota: null,
  },
];

export function DatasetTable({ datasets = defaultDatasets }: DatasetTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Dataset</TableHead>
          <TableHead>Used</TableHead>
          <TableHead>Available</TableHead>
          <TableHead>Compression</TableHead>
          <TableHead>Mountpoint</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {datasets.map((ds) => (
          <TableRow key={ds.name}>
            <TableCell className="font-medium text-mk-text-primary font-mono text-xs">
              {ds.name}
            </TableCell>
            <TableCell>{formatBytes(ds.used_bytes)}</TableCell>
            <TableCell>{formatBytes(ds.available_bytes)}</TableCell>
            <TableCell>{ds.compression}</TableCell>
            <TableCell className="font-mono text-xs">{ds.mountpoint}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
