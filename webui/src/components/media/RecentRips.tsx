/**
 * RecentRips Component
 * =====================
 * Displays a table of recently completed rip jobs.
 */

import { Badge } from "@/components/ui/badge";
import { formatBytes, formatDuration } from "@/lib/utils";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import type { RecentRip } from "@/types/media";

interface RecentRipsProps {
  rips: RecentRip[];
}

export function RecentRips({ rips }: RecentRipsProps) {
  if (rips.length === 0) {
    return (
      <p className="text-sm text-mk-text-muted p-4">No recent rips found.</p>
    );
  }

  return (
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
        {rips.map((rip) => (
          <TableRow key={rip.id}>
            <TableCell className="font-medium text-mk-text-primary">
              {rip.title}
            </TableCell>
            <TableCell className="text-mk-text-muted">{rip.date}</TableCell>
            <TableCell>{formatBytes(rip.size_bytes)}</TableCell>
            <TableCell>
              <Badge>{rip.format.toUpperCase()}</Badge>
            </TableCell>
            <TableCell>{formatDuration(rip.duration_seconds)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
