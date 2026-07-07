/**
 * ActionButton Component
 * =======================
 * Inline action button rendered within chat messages.
 * Supports: navigation, API calls, and copy-to-clipboard.
 */

import { useNavigate } from "react-router-dom";
import type { ChatAction } from "@/types/chat";
import { cn } from "@/lib/utils";

interface ActionButtonProps {
  action: ChatAction;
}

export function ActionButton({ action }: ActionButtonProps) {
  const navigate = useNavigate();

  const handleClick = () => {
    switch (action.action) {
      case "navigate":
        if (action.target) navigate(action.target);
        break;
      case "api_call":
        // Fire API call (handled by chat hook in real implementation)
        console.log("API call:", action.method, action.endpoint, action.body);
        break;
      case "copy":
        if (action.target) navigator.clipboard.writeText(action.target);
        break;
    }
  };

  return (
    <button
      onClick={handleClick}
      className={cn(
        "px-2.5 py-1 text-xs font-medium rounded-[4px]",
        "border border-mk-accent/40 text-mk-accent",
        "hover:bg-mk-accent/10 hover:border-mk-accent/60",
        "transition-all duration-[150ms]",
        "active:scale-[0.96]"
      )}
    >
      {action.label}
    </button>
  );
}
