/**
 * Dialog (Modal) Component
 * =========================
 * Overlay modal with backdrop blur and MK styling.
 */

import {
  type ReactNode,
  type HTMLAttributes,
  useEffect,
  useCallback,
} from "react";
import { cn } from "@/lib/utils";
import { X } from "lucide-react";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}

function Dialog({ open, onClose, children }: DialogProps) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose]
  );

  useEffect(() => {
    if (open) {
      document.addEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "hidden";
    }
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "";
    };
  }, [open, handleKeyDown]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[300] flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm animate-fade-in"
        onClick={onClose}
      />
      {/* Content */}
      <div className="relative animate-slide-up">{children}</div>
    </div>
  );
}

interface DialogContentProps extends HTMLAttributes<HTMLDivElement> {
  onClose?: () => void;
}

function DialogContent({ className, onClose, children, ...props }: DialogContentProps) {
  return (
    <div
      className={cn(
        "bg-mk-surface border border-mk-border rounded-[12px]",
        "shadow-lg w-full max-w-lg mx-4 p-6",
        "max-h-[85vh] overflow-y-auto",
        className
      )}
      {...props}
    >
      {onClose && (
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-mk-text-muted hover:text-mk-text-primary transition-colors"
        >
          <X size={18} />
        </button>
      )}
      {children}
    </div>
  );
}

function DialogTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2
      className={cn("text-xl font-semibold text-mk-text-primary mb-2", className)}
      {...props}
    />
  );
}

function DialogDescription({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p
      className={cn("text-sm text-mk-text-secondary mb-4", className)}
      {...props}
    />
  );
}

export { Dialog, DialogContent, DialogTitle, DialogDescription };
