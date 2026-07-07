/**
 * MobileNav Component
 * ====================
 * Slide-out navigation drawer for mobile viewports.
 * Triggered by hamburger menu in TopBar.
 */

import { useEffect } from "react";
import { useLocation, Link } from "react-router-dom";
import {
  LayoutDashboard,
  HardDrive,
  Container,
  Network,
  ShieldCheck,
  Disc3,
  Settings,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/stores/uiStore";

const navItems = [
  { label: "Dashboard", path: "/", icon: LayoutDashboard },
  { label: "Storage", path: "/storage", icon: HardDrive },
  { label: "Apps", path: "/apps", icon: Container },
  { label: "Network", path: "/network", icon: Network },
  { label: "Protection", path: "/protection", icon: ShieldCheck },
  { label: "Media", path: "/media", icon: Disc3 },
  { label: "System", path: "/system", icon: Settings },
];

export function MobileNav() {
  const location = useLocation();
  const { mobileNavOpen, setMobileNavOpen } = useUIStore();

  // Close on route change
  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname, setMobileNavOpen]);

  // Close on Escape
  useEffect(() => {
    function handleEscape(e: KeyboardEvent) {
      if (e.key === "Escape") setMobileNavOpen(false);
    }
    if (mobileNavOpen) {
      document.addEventListener("keydown", handleEscape);
    }
    return () => document.removeEventListener("keydown", handleEscape);
  }, [mobileNavOpen, setMobileNavOpen]);

  const isActive = (path: string) => {
    if (path === "/") return location.pathname === "/";
    return location.pathname.startsWith(path);
  };

  if (!mobileNavOpen) return null;

  return (
    <div className="fixed inset-0 z-[300] lg:hidden">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm animate-fade-in"
        onClick={() => setMobileNavOpen(false)}
      />

      {/* Drawer */}
      <nav
        className={cn(
          "absolute top-0 left-0 bottom-0 w-64",
          "bg-mk-surface border-r border-mk-border",
          "flex flex-col p-4",
          "animate-slide-in-right"
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-[8px] bg-mk-accent/10 border border-mk-accent/30 flex items-center justify-center">
              <span className="text-mk-accent font-bold text-sm">MK</span>
            </div>
            <span className="text-mk-text-primary font-semibold">MK OS</span>
          </div>
          <button
            onClick={() => setMobileNavOpen(false)}
            className="text-mk-text-muted hover:text-mk-text-primary transition-colors"
            aria-label="Close navigation"
          >
            <X size={20} />
          </button>
        </div>

        {/* Nav links */}
        <div className="flex flex-col gap-1">
          {navItems.map(({ label, path, icon: Icon }) => (
            <Link
              key={path}
              to={path}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-[8px] text-sm font-medium",
                "transition-colors duration-[150ms]",
                isActive(path)
                  ? "bg-mk-accent/10 text-mk-accent border border-mk-accent/20"
                  : "text-mk-text-secondary hover:text-mk-text-primary hover:bg-mk-elevated"
              )}
            >
              <Icon size={18} />
              <span>{label}</span>
            </Link>
          ))}
        </div>

        {/* Footer */}
        <div className="mt-auto pt-4 border-t border-mk-border">
          <p className="text-xs text-mk-text-muted">MK OS v1.0</p>
        </div>
      </nav>
    </div>
  );
}
