/**
 * Toggle Switch Component
 * ========================
 * On/off toggle with smooth animation and accent color.
 */

import { forwardRef, type InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface ToggleProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "onChange"> {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  label?: string;
}

const Toggle = forwardRef<HTMLInputElement, ToggleProps>(
  ({ checked, onCheckedChange, label, className, disabled, ...props }, ref) => {
    return (
      <label
        className={cn(
          "inline-flex items-center gap-2 cursor-pointer select-none",
          disabled && "opacity-50 cursor-not-allowed",
          className
        )}
      >
        <div className="relative">
          <input
            ref={ref}
            type="checkbox"
            checked={checked}
            onChange={(e) => onCheckedChange(e.target.checked)}
            disabled={disabled}
            className="sr-only peer"
            {...props}
          />
          <div
            className={cn(
              "w-9 h-5 rounded-full transition-colors duration-200",
              "peer-focus-visible:ring-2 peer-focus-visible:ring-mk-accent peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-mk-base",
              checked ? "bg-mk-accent" : "bg-mk-border-strong"
            )}
          />
          <div
            className={cn(
              "absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white",
              "transition-transform duration-200 ease-in-out",
              checked && "translate-x-4"
            )}
          />
        </div>
        {label && (
          <span className="text-sm text-mk-text-secondary">{label}</span>
        )}
      </label>
    );
  }
);
Toggle.displayName = "Toggle";

export { Toggle };
