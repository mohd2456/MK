/**
 * Badge Component
 * ================
 * Small status indicators and labels.
 */

import { type HTMLAttributes } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors",
  {
    variants: {
      variant: {
        default: "bg-mk-elevated text-mk-text-secondary border border-mk-border",
        success: "bg-mk-success/10 text-mk-success border border-mk-success/30",
        warning: "bg-mk-warning/10 text-mk-warning border border-mk-warning/30",
        error: "bg-mk-error/10 text-mk-error border border-mk-error/30",
        info: "bg-mk-info/10 text-mk-info border border-mk-info/30",
        accent: "bg-mk-accent/10 text-mk-accent border border-mk-accent/30",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
