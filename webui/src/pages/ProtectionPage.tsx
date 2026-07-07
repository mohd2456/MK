/**
 * ProtectionPage — Backups, snapshots, protection status
 */

import { RefreshCw, Shield, Camera, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { useBackupJobs, useProtectionSnapshots } from "@/hooks/useApi";

export function ProtectionPage() {
  const { data: jobsData, mutate: mj } = useBackupJobs();
  const { data: snapData, mutate: ms } = useProtectionSnapshots();

  const jobs = (jobsData as any)?.jobs ?? [];
  const snapshots = (snapData as any)?.snapshots ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-mk-text-primary">Protection</h1>
        <Button variant="secondary" size="sm" onClick={() => { mj(); ms(); }}>
          <RefreshCw size={14} /> Refresh
        </Button>
      </div>

      <Tabs defaultValue="jobs">
        <TabsList>
          <TabsTrigger value="jobs">Backup Jobs</TabsTrigger>
          <TabsTrigger value="snapshots">Snapshots</TabsTrigger>
        </TabsList>

        <TabsContent value="jobs">
          {jobs.length === 0 ? (
            <Card><CardContent className="p-6 text-center text-mk-text-muted">
              <Shield size={32} className="mx-auto mb-2 opacity-40" />
              <p>No backup jobs configured.</p>
              <p className="text-xs mt-1">Set up ZFS auto-snapshots, restic, or cron backups.</p>
            </CardContent></Card>
          ) : (
            <Table>
              <TableHeader><TableRow>
                <TableHead>Job</TableHead><TableHead>Type</TableHead>
                <TableHead>Schedule</TableHead><TableHead>Status</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {jobs.map((job: any) => (
                  <TableRow key={job.id}>
                    <TableCell className="font-medium text-mk-text-primary">{job.name}</TableCell>
                    <TableCell><Badge>{job.type}</Badge></TableCell>
                    <TableCell className="text-mk-text-muted">{job.schedule}</TableCell>
                    <TableCell>
                      <Badge variant={job.status === "active" ? "success" : "default"}>{job.status}</Badge>
                    </TableCell>
                    <TableCell>
                      <Button variant="ghost" size="icon-sm"><Play size={13} /></Button>
                    </TableCell>
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
                <TableHead>Snapshot</TableHead><TableHead>Size</TableHead><TableHead>Created</TableHead>
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
