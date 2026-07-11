/**
 * DNSConfig Component
 * ====================
 * Displays DNS configuration: primary/secondary servers, search domain, and local overrides.
 */

import { cn } from "@/lib/utils";
import type { DNSConfig as DNSConfigType } from "@/types/network";

interface DNSConfigProps {
  config: DNSConfigType;
}

export function DNSConfig({ config }: DNSConfigProps) {
  return (
    <div
      className={cn(
        "rounded-[8px] border border-mk-border bg-mk-surface p-6 space-y-4",
        "max-w-lg"
      )}
    >
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm text-mk-text-secondary">Primary DNS</span>
          <span className="text-sm font-mono text-mk-text-primary">{config.primary}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-mk-text-secondary">Secondary DNS</span>
          <span className="text-sm font-mono text-mk-text-primary">{config.secondary}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-mk-text-secondary">Search Domain</span>
          <span className="text-sm font-mono text-mk-text-primary">{config.search_domain}</span>
        </div>
      </div>

      {config.local_overrides.length > 0 && (
        <div className="border-t border-mk-border pt-4">
          <h4 className="text-sm font-semibold text-mk-text-primary mb-2">
            Local Overrides
          </h4>
          <div className="space-y-1.5">
            {config.local_overrides.map((override) => (
              <div
                key={override.hostname}
                className="flex items-center justify-between text-xs"
              >
                <span className="font-mono text-mk-text-secondary">
                  {override.hostname}
                </span>
                <span className="font-mono text-mk-text-muted">{override.ip}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
