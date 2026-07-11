/**
 * AISettings Component
 * =====================
 * Configuration form for AI provider, model, temperature, and context options.
 */

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { AISettings as AISettingsType } from "@/hooks/useApi";

interface AISettingsProps {
  settings: AISettingsType;
}

export function AISettings({ settings }: AISettingsProps) {
  return (
    <Card>
      <CardContent className="p-6 space-y-4">
        <h3 className="text-sm font-semibold text-mk-text-primary">
          AI Configuration
        </h3>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-mk-text-secondary">Provider</span>
            <Badge variant="accent">{settings.provider}</Badge>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-mk-text-secondary">Model</span>
            <span className="text-sm font-mono text-mk-text-primary">
              {settings.model}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-mk-text-secondary">Temperature</span>
            <span className="text-sm text-mk-text-primary">
              {settings.temperature}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-mk-text-secondary">Max Tokens</span>
            <span className="text-sm text-mk-text-primary">
              {settings.max_tokens}
            </span>
          </div>
        </div>

        {settings.system_prompt && (
          <div className="border-t border-mk-border pt-4">
            <p className="text-xs text-mk-text-muted mb-1">System Prompt</p>
            <p className="text-sm text-mk-text-secondary bg-mk-elevated rounded p-2 font-mono text-xs">
              {settings.system_prompt.length > 200
                ? `${settings.system_prompt.slice(0, 200)}...`
                : settings.system_prompt}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
