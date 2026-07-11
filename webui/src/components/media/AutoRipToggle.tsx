/**
 * AutoRipToggle Component
 * ========================
 * Toggle switch for auto-rip setting with description and current media settings.
 */

import { Toggle } from "@/components/ui/toggle";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { MediaSettings } from "@/types/media";

interface AutoRipToggleProps {
  settings: MediaSettings;
  onToggleAutoRip?: (enabled: boolean) => void;
}

export function AutoRipToggle({ settings, onToggleAutoRip }: AutoRipToggleProps) {
  return (
    <div
      className={cn(
        "rounded-[8px] border border-mk-border bg-mk-surface p-6 space-y-4",
        "max-w-lg"
      )}
    >
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-mk-text-primary">Auto-rip</p>
          <p className="text-xs text-mk-text-muted">
            Automatically rip when disc inserted
          </p>
        </div>
        <Toggle
          checked={settings.auto_rip}
          onCheckedChange={onToggleAutoRip ?? (() => {})}
        />
      </div>

      <div className="border-t border-mk-border pt-4 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm text-mk-text-secondary">Output path</span>
          <span className="text-sm font-mono text-mk-text-primary">
            {settings.output_path}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-mk-text-secondary">Default format</span>
          <span className="text-sm text-mk-text-primary">
            {settings.default_format.toUpperCase()} (passthrough)
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-mk-text-secondary">Min length</span>
          <span className="text-sm text-mk-text-primary">
            {settings.min_length_minutes} min
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-mk-text-secondary">Notifications</span>
          <Badge variant={settings.notifications_enabled ? "success" : "warning"}>
            {settings.notifications_enabled ? "ON" : "OFF"}
          </Badge>
        </div>
      </div>
    </div>
  );
}
