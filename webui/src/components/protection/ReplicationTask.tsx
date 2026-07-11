/**
 * ReplicationTask Component
 * ==========================
 * Displays replication tasks with source, target, status, and lag indicators.
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

export interface ReplicationTaskItem {
  task: string;
  source: string;
  target: string;
  status: string;
  lag: string;
}

interface ReplicationTaskProps {
  tasks: ReplicationTaskItem[];
}

export function ReplicationTask({ tasks }: ReplicationTaskProps) {
  if (tasks.length === 0) {
    return (
      <p className="text-sm text-mk-text-muted p-4">No replication tasks configured.</p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Task</TableHead>
          <TableHead>Source</TableHead>
          <TableHead>Target</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Lag</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {tasks.map((task) => (
          <TableRow key={task.task}>
            <TableCell className="font-medium text-mk-text-primary">
              {task.task}
            </TableCell>
            <TableCell className="font-mono text-xs">{task.source}</TableCell>
            <TableCell className="font-mono text-xs">{task.target}</TableCell>
            <TableCell>
              <Badge
                variant={
                  task.status === "Active" || task.status === "active"
                    ? "success"
                    : "warning"
                }
              >
                {task.status}
              </Badge>
            </TableCell>
            <TableCell className="text-mk-text-muted">{task.lag}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
