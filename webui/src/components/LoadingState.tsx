/**
 * LoadingState Component
 * =======================
 * A consistent loading skeleton displayed while data is being fetched.
 * Supports different variants for tables, cards, and inline content.
 */

import { cn } from "@/lib/utils";

interface LoadingStateProps {
  /** Number of skeleton rows to show */
  rows?: number;
  /** Visual variant */
  variant?: "table" | "card" | "inline";
  /** Additional class name */
  className?: string;
}

function SkeletonLine({ width = "100%" }: { width?: string }) {
  return (
    <div
      className="h-4 rounded bg-mk-border/50 animate-pulse"
      style={{ width }}
    />
  );
}

function TableSkeleton({ rows }: { rows: number }) {
  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex gap-4 pb-2 border-b border-mk-border">
        <SkeletonLine width="20%" />
        <SkeletonLine width="25%" />
        <SkeletonLine width="20%" />
        <SkeletonLine width="15%" />
        <SkeletonLine width="10%" />
      </div>
      {/* Rows */}
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-4 py-2">
          <SkeletonLine width="20%" />
          <SkeletonLine width="25%" />
          <SkeletonLine width="20%" />
          <SkeletonLine width="15%" />
          <SkeletonLine width="10%" />
        </div>
      ))}
    </div>
  );
}

function CardSkeleton({ rows }: { rows: number }) {
  return (
    <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="rounded-lg border border-mk-border bg-mk-surface p-4 space-y-3"
        >
          <SkeletonLine width="60%" />
          <SkeletonLine width="80%" />
          <SkeletonLine width="40%" />
        </div>
      ))}
    </div>
  );
}

function InlineSkeleton() {
  return (
    <div className="flex items-center gap-2">
      <div className="w-4 h-4 rounded-full bg-mk-border/50 animate-pulse" />
      <SkeletonLine width="120px" />
    </div>
  );
}

export function LoadingState({
  rows = 4,
  variant = "table",
  className,
}: LoadingStateProps) {
  return (
    <div className={cn("p-4", className)}>
      {variant === "table" && <TableSkeleton rows={rows} />}
      {variant === "card" && <CardSkeleton rows={rows} />}
      {variant === "inline" && <InlineSkeleton />}
    </div>
  );
}
