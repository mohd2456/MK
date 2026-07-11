/**
 * OfflineIndicator Component
 * ===========================
 * Displays a banner when the WebSocket connection is lost,
 * warning the user that data may be stale.
 */

import { useWebSocket } from "@/hooks/useWebSocket";
import { cn } from "@/lib/utils";

interface OfflineIndicatorProps {
  className?: string;
}

export function OfflineIndicator({ className }: OfflineIndicatorProps) {
  const { isConnected, connectionState } = useWebSocket();

  if (isConnected) return null;

  return (
    <div
      className={cn(
        "flex items-center gap-2 px-4 py-2 text-sm",
        "bg-amber-500/10 border-b border-amber-500/20",
        "text-amber-400",
        className
      )}
    >
      <div className="relative flex h-2 w-2">
        <span
          className={cn(
            "absolute inline-flex h-full w-full rounded-full opacity-75",
            connectionState === "connecting" && "animate-ping bg-amber-400",
            connectionState === "disconnected" && "bg-red-400"
          )}
        />
        <span
          className={cn(
            "relative inline-flex rounded-full h-2 w-2",
            connectionState === "connecting" ? "bg-amber-400" : "bg-red-400"
          )}
        />
      </div>
      <span>
        {connectionState === "connecting"
          ? "Reconnecting to server..."
          : "Connection lost - data may be stale"}
      </span>
    </div>
  );
}
