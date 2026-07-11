/**
 * BackupJobTable Component
 * =========================
 * Displays backup jobs with source, destination, schedule, and status badges.
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

export interface BackupJob {
  name: string;
  source: string;
  dest: string;
  schedule: string;
  status: string;
  lastRun: string;
  nextRun: string;
}

interface BackupJobTableProps {
  jobs: BackupJob[];
}

export function BackupJobTable({ jobs }: BackupJobTableProps) {
  if (jobs.length === 0) {
    return (
      <p className="text-sm text-mk-text-muted p-4">No backup jobs configured.</p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Job Name</TableHead>
          <TableHead>Source</TableHead>
          <TableHead>Destination</TableHead>
          <TableHead>Schedule</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Last Run</TableHead>
          <TableHead>Next Run</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {jobs.map((job) => (
          <TableRow key={job.name}>
            <TableCell className="font-medium text-mk-text-primary">
              {job.name}
            </TableCell>
            <TableCell className="font-mono text-xs">{job.source}</TableCell>
            <TableCell className="font-mono text-xs">{job.dest}</TableCell>
            <TableCell>{job.schedule}</TableCell>
            <TableCell>
              <Badge
                variant={
                  job.status === "OK" || job.status === "success"
                    ? "success"
                    : "error"
                }
              >
                {job.status}
              </Badge>
            </TableCell>
            <TableCell className="text-mk-text-muted text-xs">
              {job.lastRun}
            </TableCell>
            <TableCell className="text-mk-text-muted text-xs">
              {job.nextRun}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
