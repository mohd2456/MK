/**
 * PowerControls Component
 * ========================
 * Reboot and shutdown buttons with confirmation dialog.
 */

import { useState } from "react";
import { Power, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

interface PowerControlsProps {
  uptime?: string;
  onReboot?: () => void;
  onShutdown?: () => void;
}

export function PowerControls({ uptime, onReboot, onShutdown }: PowerControlsProps) {
  const [confirmAction, setConfirmAction] = useState<"reboot" | "shutdown" | null>(null);

  function handleConfirm() {
    if (confirmAction === "reboot" && onReboot) {
      onReboot();
    } else if (confirmAction === "shutdown" && onShutdown) {
      onShutdown();
    }
    setConfirmAction(null);
  }

  return (
    <Card>
      <CardContent className="p-6 space-y-6">
        {confirmAction ? (
          <div className="space-y-4">
            <p className="text-sm text-mk-text-primary font-medium">
              Are you sure you want to {confirmAction} the system?
            </p>
            <div className="flex items-center gap-3">
              <Button
                variant="destructive"
                size="sm"
                onClick={handleConfirm}
              >
                Confirm {confirmAction}
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setConfirmAction(null)}
              >
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap gap-3">
            <Button
              variant="secondary"
              size="lg"
              onClick={() => setConfirmAction("reboot")}
            >
              <RotateCcw size={16} />
              Reboot
            </Button>
            <Button
              variant="destructive"
              size="lg"
              onClick={() => setConfirmAction("shutdown")}
            >
              <Power size={16} />
              Shutdown
            </Button>
          </div>
        )}

        {uptime && (
          <div className="border-t border-mk-border pt-4 space-y-2 text-sm">
            <div className="flex items-center gap-2">
              <span className="text-mk-text-muted">Uptime:</span>
              <span className="text-mk-text-primary">{uptime}</span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
