/**
 * Tooltip Component
 * ==================
 * Simple hover tooltip using CSS-only approach for performance.
 */

import { type ReactNode, type HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface TooltipProps extends HTMLAttributes<HTMLDivElement> {
  content: string;
  children: ReactNode;
  side?: "top" | "bottom" | "left" | "right";
}

function Tooltip({ content, children, side = "top", className, ...props }: TooltipProps) {
  const positionClasses = {
    top: "bottom-full left-1/2 -translate-x-1/2 mb-2",
    bottom: "top-full left-1/2 -translate-x-1/2 mt-2",
    left: "right-full top-1/2 -translate-y-1/2 mr-2",
    right: "left-full top-1/2 -translate-y-1/2 ml-2",
  };

  return (
    <div className={cn("relative group inline-flex", className)} {...props}>
      {children}
      <div
        className={cn(
          "absolute z-[500] pointer-events-none",
          "opacity-0 group-hover:opacity-100",
          "transition-opacity duration-[150ms]",
          "px-2 py-1 rounded-[4px] text-xs font-medium",
          "bg-mk-overlay text-mk-text-primary border border-mk-border",
          "shadow-md whitespace-nowrap",
          positionClasses[side]
        )}
        role="tooltip"
      >
        {content}
      </div>
    </div>
  );
}

export { Tooltip };
