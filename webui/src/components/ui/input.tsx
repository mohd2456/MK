/**
 * Input Component
 * ================
 * Text input field styled for MK OS dark theme.
 */

import { forwardRef, type InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-9 w-full rounded-[8px] border border-mk-border",
          "bg-mk-elevated px-3 py-2 text-sm text-mk-text-primary",
          "placeholder:text-mk-text-muted",
          "focus:outline-none focus:ring-2 focus:ring-mk-accent focus:border-mk-accent",
          "disabled:cursor-not-allowed disabled:opacity-50",
          "transition-all duration-[150ms]",
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
Input.displayName = "Input";

export { Input };
