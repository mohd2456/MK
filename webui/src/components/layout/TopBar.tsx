/**
 * TopBar Component
 * =================
 * Fixed navigation bar at the top of the app.
 * Contains: MK logo, nav links, help button, chat toggle.
 *
 * Design specs:
 * - Height: 56px (h-14)
 * - Background: bg-surface with bottom border
 * - Active link: accent underline + accent text
 * - Responsive: collapses to hamburger on mobile
 */

import { useLocation, Link } from "react-router-dom";
import {
  LayoutDashboard,
  HardDrive,
  Container,
  Network,
  ShieldCheck,
  Disc3,
  FolderInput,
  Settings,
  MessageSquare,
  HelpCircle,
  Menu,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/stores/uiStore";
import { useChatStore } from "@/stores/chatStore";
import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";

const navItems = [
  { label: "Dashboard", path: "/", icon: LayoutDashboard },
  { label: "Storage", path: "/storage", icon: HardDrive },
  { label: "Apps", path: "/apps", icon: Container },
  { label: "Network", path: "/network", icon: Network },
  { label: "Protection", path: "/protection", icon: ShieldCheck },
  { label: "Media", path: "/media", icon: Disc3 },
  { label: "Drops", path: "/media-manager", icon: FolderInput },
  { label: "System", path: "/system", icon: Settings },
];

export function TopBar() {
  const location = useLocation();
  const { toggleChat, chatOpen, setMobileNavOpen } = useUIStore();
  const messages = useChatStore((s) => s.messages);

  // Check if there are unread messages (simple heuristic: last message is from assistant)
  const lastMessage = messages[messages.length - 1];
  const hasUnread = lastMessage?.role === "assistant" && !chatOpen;

  const isActive = (path: string) => {
    if (path === "/") return location.pathname === "/";
    return location.pathname.startsWith(path);
  };

  return (
    <header className="h-14 bg-mk-surface border-b border-mk-border flex items-center px-4 gap-1 shrink-0 z-[200]">
      {/* Mobile hamburger */}
      <Button
        variant="ghost"
        size="icon-sm"
        className="lg:hidden mr-2"
        onClick={() => setMobileNavOpen(true)}
        aria-label="Open navigation menu"
      >
        <Menu size={20} />
      </Button>

      {/* Logo */}
      <Link
        to="/"
        className="flex items-center gap-2 mr-6 shrink-0"
        aria-label="MK OS Home"
      >
        <div className="w-8 h-8 rounded-[8px] bg-mk-accent/10 border border-mk-accent/30 flex items-center justify-center">
          <span className="text-mk-accent font-bold text-sm">MK</span>
        </div>
        <span className="text-mk-text-primary font-semibold text-sm hidden sm:block">
          MK OS
        </span>
      </Link>

      {/* Navigation links - hidden on mobile */}
      <nav className="hidden lg:flex items-center gap-0.5 flex-1">
        {navItems.map(({ label, path, icon: Icon }) => (
          <Link
            key={path}
            to={path}
            className={cn(
              "relative flex items-center gap-1.5 px-3 py-2 rounded-[4px] text-sm font-medium",
              "transition-colors duration-[150ms]",
              isActive(path)
                ? "text-mk-accent"
                : "text-mk-text-muted hover:text-mk-text-primary hover:bg-mk-elevated"
            )}
          >
            <Icon size={16} />
            <span>{label}</span>
            {isActive(path) && (
              <span className="absolute bottom-0 left-3 right-3 h-0.5 bg-mk-accent rounded-full" />
            )}
          </Link>
        ))}
      </nav>

      {/* Right side actions */}
      <div className="flex items-center gap-1 ml-auto">
        <Tooltip content="Help" side="bottom">
          <Button variant="ghost" size="icon" aria-label="Help">
            <HelpCircle size={18} className="text-mk-text-muted" />
          </Button>
        </Tooltip>

        <Tooltip content={chatOpen ? "Close chat (Ctrl+/)" : "Open chat (Ctrl+/)"} side="bottom">
          <Button
            variant={chatOpen ? "accent_ghost" : "ghost"}
            size="icon"
            onClick={toggleChat}
            aria-label="Toggle chat panel"
            className="relative"
          >
            <MessageSquare size={18} />
            {hasUnread && (
              <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-mk-accent rounded-full animate-pulse-slow" />
            )}
          </Button>
        </Tooltip>
      </div>
    </header>
  );
}
