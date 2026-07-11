/**
 * EmptyState Component
 * =====================
 * A styled placeholder shown when a data list or table has no items.
 * Supports an icon, title, description, and optional action button.
 */

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

interface EmptyStateProps {
  /** Icon element to display */
  icon?: ReactNode;
  /** Main heading text */
  title: string;
  /** Descriptive subtext */
  description?: string;
  /** Optional action button label */
  actionLabel?: string;
  /** Action button click handler */
  onAction?: () => void;
  /** Additional class name */
  className?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  actionLabel,
  onAction,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center min-h-[200px] p-8 rounded-lg border border-dashed border-mk-border bg-mk-surface/50",
        className
      )}
    >
      {icon && (
        <div className="w-12 h-12 mb-4 rounded-full bg-mk-accent/10 flex items-center justify-center text-mk-accent">
          {icon}
        </div>
      )}
      <h3 className="text-lg font-semibold text-mk-text-primary">{title}</h3>
      {description && (
        <p className="text-sm text-mk-text-muted mt-1 text-center max-w-sm">
          {description}
        </p>
      )}
      {actionLabel && onAction && (
        <Button onClick={onAction} variant="secondary" size="sm" className="mt-4">
          {actionLabel}
        </Button>
      )}
    </div>
  );
}
