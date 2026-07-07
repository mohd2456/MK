/**
 * Dropdown Menu Component
 * ========================
 * Simple dropdown menu with trigger button.
 * Uses click-outside and Escape to close.
 */

import {
  useState,
  useRef,
  useEffect,
  type ReactNode,
  type HTMLAttributes,
} from "react";
import { cn } from "@/lib/utils";

interface DropdownMenuProps {
  trigger: ReactNode;
  children: ReactNode;
  align?: "left" | "right";
}

function DropdownMenu({ trigger, children, align = "right" }: DropdownMenuProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function handleEscape(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }

    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("keydown", handleEscape);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [open]);

  return (
    <div className="relative inline-flex" ref={ref}>
      <div onClick={() => setOpen(!open)}>{trigger}</div>
      {open && (
        <div
          className={cn(
            "absolute top-full mt-1 z-[100]",
            "min-w-[160px] py-1",
            "bg-mk-overlay border border-mk-border rounded-[8px]",
            "shadow-lg animate-fade-in",
            align === "right" ? "right-0" : "left-0"
          )}
          onClick={() => setOpen(false)}
        >
          {children}
        </div>
      )}
    </div>
  );
}

interface DropdownItemProps extends HTMLAttributes<HTMLButtonElement> {
  destructive?: boolean;
}

function DropdownItem({ className, destructive, ...props }: DropdownItemProps) {
  return (
    <button
      className={cn(
        "w-full text-left px-3 py-2 text-sm transition-colors",
        "hover:bg-mk-elevated",
        destructive
          ? "text-mk-error hover:bg-mk-error/10"
          : "text-mk-text-secondary hover:text-mk-text-primary",
        className
      )}
      {...props}
    />
  );
}

function DropdownSeparator() {
  return <div className="my-1 h-px bg-mk-border" />;
}

export { DropdownMenu, DropdownItem, DropdownSeparator };
