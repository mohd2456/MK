/**
 * MainLayout Component
 * =====================
 * Root layout that composes: TopBar + Main Content + Chat Panel.
 * This is the authenticated wrapper - all pages render within it.
 *
 * Layout:
 * ┌─────────────────────────────────────┐
 * │ TopBar (h-14, full width)           │
 * ├──────────────────────────┬──────────┤
 * │                          │          │
 * │   Main Content (flex-1)  │  Chat    │
 * │   (scrollable)           │  Panel   │
 * │                          │  (w-96)  │
 * │                          │          │
 * └──────────────────────────┴──────────┘
 */

import { Outlet } from "react-router-dom";
import { TopBar } from "./TopBar";
import { ChatPanel } from "./ChatPanel";
import { MobileNav } from "./MobileNav";

export function MainLayout() {
  return (
    <div className="flex flex-col h-full w-full overflow-hidden bg-mk-base">
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        {/* Main content area */}
        <main className="flex-1 overflow-y-auto overflow-x-hidden">
          <div className="max-w-[1400px] mx-auto p-6">
            <Outlet />
          </div>
        </main>

        {/* Chat sidebar */}
        <ChatPanel />
      </div>

      {/* Mobile navigation drawer */}
      <MobileNav />
    </div>
  );
}
