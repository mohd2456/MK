/**
 * QuickActions Component
 * =======================
 * Grid of one-click action buttons for common operations.
 * Designed for speed - no confirmation for reversible actions.
 */

import { Play, RefreshCw, Disc3, Download } from "lucide-react";
import { Button } from "@/components/ui/button";

interface QuickAction {
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
}

interface QuickActionsProps {
  actions?: QuickAction[];
}

const defaultActions: QuickAction[] = [
  {
    label: "Start Backup",
    icon: <Play size={14} />,
    onClick: () => console.log("Start backup"),
  },
  {
    label: "Update System",
    icon: <Download size={14} />,
    onClick: () => console.log("Update system"),
  },
  {
    label: "Rip Disc",
    icon: <Disc3 size={14} />,
    onClick: () => console.log("Rip disc"),
  },
  {
    label: "Restart Service",
    icon: <RefreshCw size={14} />,
    onClick: () => console.log("Restart service"),
  },
];

export function QuickActions({ actions = defaultActions }: QuickActionsProps) {
  return (
    <div className="rounded-[8px] border border-mk-border bg-mk-surface p-4">
      <h3 className="text-sm font-semibold text-mk-text-primary mb-3">
        Quick Actions
      </h3>
      <div className="flex flex-col gap-2">
        {actions.map((action) => (
          <Button
            key={action.label}
            variant="secondary"
            size="sm"
            onClick={action.onClick}
            className="justify-start w-full"
          >
            {action.icon}
            <span>{action.label}</span>
          </Button>
        ))}
      </div>
    </div>
  );
}
