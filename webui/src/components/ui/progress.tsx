/**
 * Progress Bar Component
 * =======================
 * Horizontal progress indicator with color-coded thresholds.
 */

import { forwardRef, type HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface ProgressProps extends HTMLAttributes<HTMLDivElement> {
  value: number; // 0-100
  max?: number;
  /** Color variant - auto picks based on value if "auto" */
  variant?: "default" | "success" | "warning" | "error" | "accent" | "auto";
  /** Show text label inside or beside the bar */
  showLabel?: boolean;
  /** Height of the bar */
  size?: "sm" | "md" | "lg";
}

const Progress = forwardRef<HTMLDivElement, ProgressProps>(
  (
    { value, max = 100, variant = "auto", showLabel = false, size = "md", className, ...props },
    ref
  ) => {
    const percent = Math.min(100, Math.max(0, (value / max) * 100));

    // Auto-color based on percentage thresholds
    const resolvedVariant =
      variant === "auto"
        ? percent >= 90
          ? "error"
          : percent >= 75
            ? "warning"
            : "accent"
        : variant;

    const colorMap = {
      default: "bg-mk-text-muted",
      success: "bg-mk-success",
      warning: "bg-mk-warning",
      error: "bg-mk-error",
      accent: "bg-mk-accent",
    };

    const sizeMap = {
      sm: "h-1.5",
      md: "h-2.5",
      lg: "h-4",
    };

    return (
      <div className={cn("flex items-center gap-2 w-full", className)} ref={ref} {...props}>
        <div
          className={cn(
            "flex-1 rounded-full bg-mk-elevated overflow-hidden",
            sizeMap[size]
          )}
        >
          <div
            className={cn(
              "h-full rounded-full transition-all duration-500 ease-out",
              colorMap[resolvedVariant]
            )}
            style={{ width: `${percent}%` }}
          />
        </div>
        {showLabel && (
          <span className="text-xs text-mk-text-secondary font-medium min-w-[3ch] text-right">
            {Math.round(percent)}%
          </span>
        )}
      </div>
    );
  }
);
Progress.displayName = "Progress";

export { Progress };
