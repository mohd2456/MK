/**
 * ScrubSchedule Component
 * =========================
 * Displays ZFS pool scrub schedules with last run, duration, and error count.
 */

import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";

export interface ScrubScheduleItem {
  pool: string;
  schedule: string;
  lastRun: string;
  duration: string;
  errors: number;
}

interface ScrubScheduleProps {
  schedules: ScrubScheduleItem[];
}

export function ScrubSchedule({ schedules }: ScrubScheduleProps) {
  if (schedules.length === 0) {
    return (
      <p className="text-sm text-mk-text-muted p-4">No scrub schedules configured.</p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Pool</TableHead>
          <TableHead>Schedule</TableHead>
          <TableHead>Last Run</TableHead>
          <TableHead>Duration</TableHead>
          <TableHead>Errors</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {schedules.map((scrub) => (
          <TableRow key={scrub.pool}>
            <TableCell className="font-medium text-mk-text-primary font-mono">
              {scrub.pool}
            </TableCell>
            <TableCell>{scrub.schedule}</TableCell>
            <TableCell className="text-mk-text-muted">{scrub.lastRun}</TableCell>
            <TableCell>{scrub.duration}</TableCell>
            <TableCell>
              <Badge variant={scrub.errors === 0 ? "success" : "error"}>
                {scrub.errors}
              </Badge>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
