/**
 * VMTable Component
 * ==================
 * Virtual machine list with status, resources, and controls.
 */

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { formatBytes } from "@/lib/utils";
import { Play, Square, Monitor } from "lucide-react";
import type { VM, VMStatus } from "@/types/apps";

interface VMTableProps {
  vms?: VM[];
}

const defaultVMs: VM[] = [
  { id: "v1", name: "win11-dev", os: "Windows 11", vcpu: 4, ram_bytes: 8 * 1024 ** 3, status: "running", disk_size_bytes: 100 * 1024 ** 3, vnc_port: 5900 },
  { id: "v2", name: "ubuntu-lab", os: "Ubuntu 24.04", vcpu: 2, ram_bytes: 4 * 1024 ** 3, status: "stopped", disk_size_bytes: 50 * 1024 ** 3 },
];

const statusBadge: Record<VMStatus, { variant: "success" | "default" | "warning" | "error"; label: string }> = {
  running: { variant: "success", label: "Running" },
  stopped: { variant: "default", label: "Stopped" },
  paused: { variant: "warning", label: "Paused" },
  error: { variant: "error", label: "Error" },
};

export function VMTable({ vms = defaultVMs }: VMTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>OS</TableHead>
          <TableHead>vCPU</TableHead>
          <TableHead>RAM</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {vms.map((vm) => {
          const badge = statusBadge[vm.status];
          return (
            <TableRow key={vm.id}>
              <TableCell className="font-medium text-mk-text-primary">
                {vm.name}
              </TableCell>
              <TableCell>{vm.os}</TableCell>
              <TableCell>{vm.vcpu}</TableCell>
              <TableCell>{formatBytes(vm.ram_bytes)}</TableCell>
              <TableCell>
                <Badge variant={badge.variant}>{badge.label}</Badge>
              </TableCell>
              <TableCell className="text-right">
                <div className="flex items-center gap-1 justify-end">
                  {vm.status === "running" ? (
                    <>
                      <Button variant="ghost" size="icon-sm" aria-label="Console">
                        <Monitor size={13} />
                      </Button>
                      <Button variant="ghost" size="icon-sm" aria-label="Stop">
                        <Square size={13} />
                      </Button>
                    </>
                  ) : (
                    <Button variant="ghost" size="icon-sm" aria-label="Start">
                      <Play size={13} />
                    </Button>
                  )}
                </div>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
