/**
 * StackCard Component
 * ====================
 * Docker Compose stack card with service count and health indicator.
 */

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RotateCcw, Edit, MoreHorizontal } from "lucide-react";
import type { Stack, StackHealth } from "@/types/apps";

interface StackCardProps {
  stacks?: Stack[];
}

const defaultStacks: Stack[] = [
  { name: "media-stack", services_total: 5, services_running: 5, health: "healthy", compose_file: "/opt/stacks/media/compose.yml", created: "" },
  { name: "monitoring", services_total: 3, services_running: 3, health: "healthy", compose_file: "/opt/stacks/monitoring/compose.yml", created: "" },
  { name: "dev-tools", services_total: 4, services_running: 2, health: "degraded", compose_file: "/opt/stacks/dev/compose.yml", created: "" },
];

const healthBadge: Record<StackHealth, "success" | "warning" | "error"> = {
  healthy: "success",
  degraded: "warning",
  down: "error",
};

export function StackCard({ stacks = defaultStacks }: StackCardProps) {
  return (
    <div className="space-y-3">
      {stacks.map((stack) => (
        <div
          key={stack.name}
          className={cn(
            "rounded-[8px] border border-mk-border bg-mk-surface p-4",
            "hover:border-mk-border-strong transition-colors"
          )}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <h4 className="text-sm font-semibold text-mk-text-primary">
                    {stack.name}
                  </h4>
                  <Badge variant={healthBadge[stack.health]}>
                    {stack.health}
                  </Badge>
                </div>
                <p className="text-xs text-mk-text-muted mt-0.5">
                  {stack.services_running}/{stack.services_total} services up
                </p>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <Button variant="ghost" size="icon-sm" aria-label="Restart stack">
                <RotateCcw size={13} />
              </Button>
              <Button variant="ghost" size="icon-sm" aria-label="Edit stack">
                <Edit size={13} />
              </Button>
              <Button variant="ghost" size="icon-sm" aria-label="More options">
                <MoreHorizontal size={13} />
              </Button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
