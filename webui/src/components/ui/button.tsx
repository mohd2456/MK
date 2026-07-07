/**
 * Button Component
 * =================
 * Versatile button with variants matching MK OS design system.
 */

import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  [
    "inline-flex items-center justify-center gap-2",
    "font-medium whitespace-nowrap",
    "transition-all duration-[150ms] ease-in-out",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mk-accent focus-visible:ring-offset-2 focus-visible:ring-offset-mk-base",
    "disabled:pointer-events-none disabled:opacity-50",
    "cursor-pointer select-none",
  ].join(" "),
  {
    variants: {
      variant: {
        default: [
          "bg-mk-accent text-mk-base",
          "hover:bg-mk-accent-hover hover:shadow-[0_0_20px_rgba(0,212,255,0.25)]",
          "active:scale-[0.97]",
        ].join(" "),
        secondary: [
          "bg-mk-elevated text-mk-text-primary border border-mk-border",
          "hover:bg-mk-overlay hover:border-mk-border-strong",
          "active:scale-[0.97]",
        ].join(" "),
        ghost: [
          "text-mk-text-secondary",
          "hover:bg-mk-elevated hover:text-mk-text-primary",
        ].join(" "),
        destructive: [
          "bg-mk-error/10 text-mk-error border border-mk-error/30",
          "hover:bg-mk-error/20 hover:border-mk-error/50",
          "active:scale-[0.97]",
        ].join(" "),
        outline: [
          "border border-mk-border text-mk-text-primary bg-transparent",
          "hover:bg-mk-elevated hover:border-mk-border-strong",
          "active:scale-[0.97]",
        ].join(" "),
        accent_ghost: [
          "text-mk-accent",
          "hover:bg-mk-accent/10",
        ].join(" "),
      },
      size: {
        sm: "h-9 px-3 text-[13px] rounded-[6px]",
        md: "h-10 px-4 text-sm rounded-[8px]",
        lg: "h-12 px-6 text-base rounded-[8px]",
        icon: "h-10 w-10 rounded-[8px]",
        "icon-sm": "h-9 w-9 rounded-[6px]",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "md",
    },
  }
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => {
    return (
      <button
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
