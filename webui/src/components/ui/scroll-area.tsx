/**
 * Scroll Area Component
 * ======================
 * A container that handles overflow with styled scrollbars.
 * Thin, dark scrollbar that matches the MK theme.
 */

import { forwardRef, type HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface ScrollAreaProps extends HTMLAttributes<HTMLDivElement> {
  /** Direction to allow scrolling */
  orientation?: "vertical" | "horizontal" | "both";
}

const ScrollArea = forwardRef<HTMLDivElement, ScrollAreaProps>(
  ({ orientation = "vertical", className, children, ...props }, ref) => {
    const overflowClass = {
      vertical: "overflow-y-auto overflow-x-hidden",
      horizontal: "overflow-x-auto overflow-y-hidden",
      both: "overflow-auto",
    };

    return (
      <div
        ref={ref}
        className={cn("relative", overflowClass[orientation], className)}
        {...props}
      >
        {children}
      </div>
    );
  }
);
ScrollArea.displayName = "ScrollArea";

export { ScrollArea };
