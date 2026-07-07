/**
 * QuickActions Component
 * =======================
 * Grid of one-click action buttons for common operations.
 * Wired to real API endpoints.
 */

import { useState } from "react";
import { Play, RefreshCw, Disc3, Download, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { post } from "@/lib/api";

export function QuickActions() {
  const [loading, setLoading] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  async function handleAction(label: string, action: () => Promise<unknown>) {
    setLoading(label);
    setFeedback(null);
    try {
      await action();
      setFeedback(`${label}: Done`);
    } catch (e: any) {
      setFeedback(`${label}: Failed`);
    } finally {
      setLoading(null);
      setTimeout(() => setFeedback(null), 3000);
    }
  }

  const actions = [
    {
      label: "Restart MK",
      icon: <RefreshCw size={14} />,
      onClick: () =>
        handleAction("Restart MK", () =>
          post("/apps/containers/mk-web/restart")
        ),
    },
    {
      label: "System Health",
      icon: <Play size={14} />,
      onClick: () =>
        handleAction("System Health", async () => {
          const res = await fetch("/api/v1/system/health", { credentials: "include" });
          if (!res.ok) throw new Error("Failed");
          return res.json();
        }),
    },
    {
      label: "Scan Media",
      icon: <Disc3 size={14} />,
      onClick: () =>
        handleAction("Scan Media", () =>
          post("/media/organize", { source: "/mnt/drops", dry_run: true })
        ),
    },
    {
      label: "Check Updates",
      icon: <Download size={14} />,
      onClick: () =>
        handleAction("Check Updates", async () => {
          const res = await fetch("/api/v1/system/info", { credentials: "include" });
          if (!res.ok) throw new Error("Failed");
          return res.json();
        }),
    },
  ];

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
            disabled={loading === action.label}
            className="justify-start w-full"
          >
            {loading === action.label ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              action.icon
            )}
            <span>{action.label}</span>
          </Button>
        ))}
      </div>
      {feedback && (
        <p className="text-xs text-mk-text-muted mt-2">{feedback}</p>
      )}
    </div>
  );
}
