/**
 * ServiceTable Component
 * =======================
 * Displays systemd services with status badges and start/stop/restart actions.
 */

import { Play, Square, RotateCcw, Loader2 } from "lucide-react";
import { useState } from "react";
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
import type { SystemService } from "@/types/system";

interface ServiceTableProps {
  services: SystemService[];
  onAction?: (name: string, action: "start" | "stop" | "restart") => Promise<void>;
}

const statusVariant: Record<string, "success" | "error" | "warning"> = {
  running: "success",
  stopped: "warning",
  failed: "error",
  inactive: "warning",
};

export function ServiceTable({ services, onAction }: ServiceTableProps) {
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  async function handleAction(name: string, action: "start" | "stop" | "restart") {
    if (!onAction) return;
    setActionLoading(`${name}-${action}`);
    try {
      await onAction(name, action);
    } finally {
      setActionLoading(null);
    }
  }

  if (services.length === 0) {
    return (
      <p className="text-sm text-mk-text-muted p-4">No services found.</p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Service</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>CPU</TableHead>
          <TableHead>RAM</TableHead>
          <TableHead>Uptime</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {services.map((svc) => (
          <TableRow key={svc.name}>
            <TableCell>
              <div>
                <span className="font-medium text-mk-text-primary">{svc.name}</span>
                {svc.description && (
                  <p className="text-xs text-mk-text-muted">{svc.description}</p>
                )}
              </div>
            </TableCell>
            <TableCell>
              <Badge variant={statusVariant[svc.status] ?? "warning"}>
                {svc.status}
              </Badge>
            </TableCell>
            <TableCell className="text-xs">{svc.cpu_percent}%</TableCell>
            <TableCell className="text-xs">
              {Math.round(svc.ram_bytes / 1024 / 1024)} MB
            </TableCell>
            <TableCell className="text-xs text-mk-text-muted">{svc.uptime}</TableCell>
            <TableCell className="text-right">
              <div className="flex items-center justify-end gap-1">
                {svc.status === "running" ? (
                  <>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Restart ${svc.name}`}
                      disabled={actionLoading === `${svc.name}-restart`}
                      onClick={() => handleAction(svc.name, "restart")}
                    >
                      {actionLoading === `${svc.name}-restart` ? (
                        <Loader2 size={13} className="animate-spin" />
                      ) : (
                        <RotateCcw size={13} />
                      )}
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Stop ${svc.name}`}
                      disabled={actionLoading === `${svc.name}-stop`}
                      onClick={() => handleAction(svc.name, "stop")}
                    >
                      {actionLoading === `${svc.name}-stop` ? (
                        <Loader2 size={13} className="animate-spin" />
                      ) : (
                        <Square size={13} />
                      )}
                    </Button>
                  </>
                ) : (
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Start ${svc.name}`}
                    disabled={actionLoading === `${svc.name}-start`}
                    onClick={() => handleAction(svc.name, "start")}
                  >
                    {actionLoading === `${svc.name}-start` ? (
                      <Loader2 size={13} className="animate-spin" />
                    ) : (
                      <Play size={13} />
                    )}
                  </Button>
                )}
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
