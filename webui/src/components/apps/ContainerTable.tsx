/**
 * ContainerTable Component
 * =========================
 * Live-updating table of Docker containers with status, CPU, RAM.
 */

import { cn, formatBytes } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownItem, DropdownSeparator } from "@/components/ui/dropdown-menu";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { MoreHorizontal, Play, Square, RotateCcw } from "lucide-react";
import type { Container, ContainerStatus } from "@/types/apps";

interface ContainerTableProps {
  containers?: Container[];
}

const defaultContainers: Container[] = [
  { id: "c1", name: "plex", image: "plexinc/pms-docker", status: "running", cpu_percent: 12, ram_bytes: 2.1 * 1024 ** 3, uptime: "47d", ports: ["32400:32400"], created: "" },
  { id: "c2", name: "sonarr", image: "linuxserver/sonarr", status: "running", cpu_percent: 2, ram_bytes: 512 * 1024 ** 2, uptime: "47d", ports: ["8989:8989"], created: "" },
  { id: "c3", name: "radarr", image: "linuxserver/radarr", status: "running", cpu_percent: 1, ram_bytes: 480 * 1024 ** 2, uptime: "47d", ports: ["7878:7878"], created: "" },
  { id: "c4", name: "nginx-proxy", image: "jwilder/nginx-proxy", status: "running", cpu_percent: 0, ram_bytes: 64 * 1024 ** 2, uptime: "47d", ports: ["80:80", "443:443"], created: "" },
  { id: "c5", name: "db-postgres", image: "postgres:16", status: "stopped", cpu_percent: 0, ram_bytes: 0, uptime: "-", ports: ["5432:5432"], created: "" },
];

const statusBadge: Record<ContainerStatus, { variant: "success" | "default" | "warning" | "error"; label: string }> = {
  running: { variant: "success", label: "Running" },
  stopped: { variant: "default", label: "Stopped" },
  restarting: { variant: "warning", label: "Restarting" },
  error: { variant: "error", label: "Error" },
};

export function ContainerTable({ containers = defaultContainers }: ContainerTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Image</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>CPU</TableHead>
          <TableHead>RAM</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {containers.map((container) => {
          const badge = statusBadge[container.status];
          return (
            <TableRow key={container.id}>
              <TableCell className="font-medium text-mk-text-primary">
                {container.name}
              </TableCell>
              <TableCell className="font-mono text-xs max-w-[200px] truncate">
                {container.image}
              </TableCell>
              <TableCell>
                <Badge variant={badge.variant}>{badge.label}</Badge>
              </TableCell>
              <TableCell>
                <span className={cn(container.cpu_percent > 50 && "text-mk-warning")}>
                  {container.status === "running" ? `${container.cpu_percent}%` : "-"}
                </span>
              </TableCell>
              <TableCell>
                {container.status === "running" ? formatBytes(container.ram_bytes) : "-"}
              </TableCell>
              <TableCell className="text-right">
                <DropdownMenu
                  trigger={
                    <Button variant="ghost" size="icon-sm">
                      <MoreHorizontal size={14} />
                    </Button>
                  }
                >
                  {container.status === "running" ? (
                    <>
                      <DropdownItem>
                        <span className="flex items-center gap-2"><Square size={12} /> Stop</span>
                      </DropdownItem>
                      <DropdownItem>
                        <span className="flex items-center gap-2"><RotateCcw size={12} /> Restart</span>
                      </DropdownItem>
                    </>
                  ) : (
                    <DropdownItem>
                      <span className="flex items-center gap-2"><Play size={12} /> Start</span>
                    </DropdownItem>
                  )}
                  <DropdownItem>View Logs</DropdownItem>
                  <DropdownSeparator />
                  <DropdownItem destructive>Remove</DropdownItem>
                </DropdownMenu>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
