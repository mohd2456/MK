/**
 * ProtectionPage
 * ===============
 * Backup jobs, scrub schedules, replication, and retention policies.
 */

import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";

// Mock data
const backupJobs = [
  { name: "daily-media", source: "tank/media", dest: "backup/media", schedule: "Daily 2AM", status: "OK", lastRun: "2024-01-15 02:00", nextRun: "2024-01-16 02:00" },
  { name: "weekly-full", source: "tank", dest: "offsite-s3", schedule: "Sun 3AM", status: "OK", lastRun: "2024-01-14 03:00", nextRun: "2024-01-21 03:00" },
  { name: "apps-config", source: "tank/apps", dest: "backup/apps", schedule: "Every 6h", status: "OK", lastRun: "2024-01-15 12:00", nextRun: "2024-01-15 18:00" },
  { name: "db-dump", source: "postgres", dest: "tank/backups", schedule: "Every 1h", status: "FAILED", lastRun: "2024-01-15 14:00", nextRun: "2024-01-15 15:00" },
];

const scrubSchedules = [
  { pool: "tank", schedule: "Sun 1AM", lastRun: "2024-01-14", duration: "4h 12m", errors: 0 },
  { pool: "fast", schedule: "Wed/Sun 3AM", lastRun: "2024-01-15", duration: "12m", errors: 0 },
  { pool: "backup", schedule: "1st Sun 2AM", lastRun: "2024-01-07", duration: "6h 30m", errors: 0 },
];

const replicationTasks = [
  { task: "offsite-sync", source: "tank", target: "remote:backup", status: "Active", lag: "2h" },
  { task: "local-mirror", source: "fast", target: "tank/mirror", status: "Active", lag: "10m" },
];

const retentionPolicies = [
  { name: "standard", keepDaily: 7, keepWeekly: 4, keepMonthly: 12 },
  { name: "critical", keepDaily: 30, keepWeekly: 12, keepMonthly: 24 },
  { name: "minimal", keepDaily: 3, keepWeekly: 2, keepMonthly: 3 },
];

export function ProtectionPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-mk-text-primary">Data Protection</h1>
        <Button size="sm">
          <Plus size={14} />
          Create Job
        </Button>
      </div>

      <Tabs defaultValue="backups">
        <TabsList>
          <TabsTrigger value="backups">Backup Jobs</TabsTrigger>
          <TabsTrigger value="scrubs">Scrub Schedule</TabsTrigger>
          <TabsTrigger value="replication">Replication</TabsTrigger>
          <TabsTrigger value="retention">Retention</TabsTrigger>
        </TabsList>

        {/* Backup Jobs */}
        <TabsContent value="backups">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Job Name</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Destination</TableHead>
                <TableHead>Schedule</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Last Run</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {backupJobs.map((job) => (
                <TableRow key={job.name}>
                  <TableCell className="font-medium text-mk-text-primary">
                    {job.name}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{job.source}</TableCell>
                  <TableCell className="font-mono text-xs">{job.dest}</TableCell>
                  <TableCell>{job.schedule}</TableCell>
                  <TableCell>
                    <Badge variant={job.status === "OK" ? "success" : "error"}>
                      {job.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-mk-text-muted text-xs">
                    {job.lastRun}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TabsContent>

        {/* Scrub Schedule */}
        <TabsContent value="scrubs">
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
              {scrubSchedules.map((scrub) => (
                <TableRow key={scrub.pool}>
                  <TableCell className="font-medium text-mk-text-primary font-mono">
                    {scrub.pool}
                  </TableCell>
                  <TableCell>{scrub.schedule}</TableCell>
                  <TableCell>{scrub.lastRun}</TableCell>
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
        </TabsContent>

        {/* Replication */}
        <TabsContent value="replication">
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
              {replicationTasks.map((task) => (
                <TableRow key={task.task}>
                  <TableCell className="font-medium text-mk-text-primary">
                    {task.task}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{task.source}</TableCell>
                  <TableCell className="font-mono text-xs">{task.target}</TableCell>
                  <TableCell>
                    <Badge variant="success">{task.status}</Badge>
                  </TableCell>
                  <TableCell className="text-mk-text-muted">{task.lag}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TabsContent>

        {/* Retention */}
        <TabsContent value="retention">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Policy Name</TableHead>
                <TableHead>Keep Daily</TableHead>
                <TableHead>Keep Weekly</TableHead>
                <TableHead>Keep Monthly</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {retentionPolicies.map((policy) => (
                <TableRow key={policy.name}>
                  <TableCell className="font-medium text-mk-text-primary">
                    {policy.name}
                  </TableCell>
                  <TableCell>{policy.keepDaily}</TableCell>
                  <TableCell>{policy.keepWeekly}</TableCell>
                  <TableCell>{policy.keepMonthly}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TabsContent>
      </Tabs>
    </div>
  );
}
