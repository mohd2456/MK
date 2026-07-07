/**
 * PoolCard Component
 * ===================
 * Displays a ZFS pool with name, layout, usage bar, health badge, and actions.
 */

import { cn } from "@/lib/utils";
import { formatBytes } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownItem, DropdownSeparator } from "@/components/ui/dropdown-menu";
import { MoreHorizontal } from "lucide-react";
import type { Pool } from "@/types/storage";

interface PoolCardProps {
  pool: Pool;
}

const healthBadgeVariant: Record<string, "success" | "warning" | "error"> = {
  ONLINE: "success",
  DEGRADED: "warning",
  FAULTED: "error",
  OFFLINE: "error",
};

export function PoolCard({ pool }: PoolCardProps) {
  return (
    <div
      className={cn(
        "rounded-[8px] border border-mk-border bg-mk-surface p-4",
        "hover:border-mk-border-strong transition-colors duration-200"
      )}
    >
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2">
            <h4 className="text-sm font-semibold text-mk-text-primary">
              {pool.name}
            </h4>
            <Badge variant={healthBadgeVariant[pool.health] ?? "error"}>
              {pool.health}
            </Badge>
          </div>
          <p className="text-xs text-mk-text-muted mt-0.5">
            {pool.layout} &middot; {pool.disk_count} disks
          </p>
        </div>

        <DropdownMenu
          trigger={
            <Button variant="ghost" size="icon-sm">
              <MoreHorizontal size={14} />
            </Button>
          }
        >
          <DropdownItem>View Details</DropdownItem>
          <DropdownItem>Scrub Now</DropdownItem>
          <DropdownItem>Add Disk</DropdownItem>
          <DropdownSeparator />
          <DropdownItem destructive>Export Pool</DropdownItem>
        </DropdownMenu>
      </div>

      {/* Usage bar */}
      <div className="space-y-1.5">
        <Progress value={pool.usage_percent} variant="auto" size="md" />
        <div className="flex justify-between text-xs text-mk-text-muted">
          <span>{formatBytes(pool.used_bytes)} used</span>
          <span>{formatBytes(pool.size_bytes)} total</span>
        </div>
      </div>
    </div>
  );
}
