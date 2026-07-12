/**
 * ActionButton Component
 * =======================
 * Inline action button rendered within chat messages.
 * Supports: navigation, API calls, and copy-to-clipboard.
 */

import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Check, X as XIcon, Loader2 } from "lucide-react";
import type { ChatAction } from "@/types/chat";
import { cn } from "@/lib/utils";
import { get, post, put, del } from "@/lib/api";
import { API_BASE } from "@/lib/constants";

interface ActionButtonProps {
  action: ChatAction;
}

type Status = "idle" | "pending" | "done" | "error";

/** Normalize an endpoint so it's relative to the api client's API_BASE. */
function normalizeEndpoint(endpoint: string): string {
  if (endpoint.startsWith(API_BASE)) return endpoint.slice(API_BASE.length) || "/";
  return endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
}

async function callApi(action: ChatAction): Promise<void> {
  const endpoint = normalizeEndpoint(action.endpoint ?? "");
  const method = (action.method ?? "POST").toUpperCase();
  switch (method) {
    case "GET":
      await get(endpoint);
      break;
    case "PUT":
      await put(endpoint, action.body);
      break;
    case "DELETE":
      await del(endpoint);
      break;
    default:
      await post(endpoint, action.body);
  }
}

export function ActionButton({ action }: ActionButtonProps) {
  const navigate = useNavigate();
  const [status, setStatus] = useState<Status>("idle");

  const handleClick = useCallback(async () => {
    switch (action.action) {
      case "navigate":
        if (action.target) navigate(action.target);
        break;
      case "copy":
        if (action.target) {
          try {
            await navigator.clipboard.writeText(action.target);
            setStatus("done");
            setTimeout(() => setStatus("idle"), 1500);
          } catch {
            setStatus("error");
            setTimeout(() => setStatus("idle"), 2000);
          }
        }
        break;
      case "api_call":
        if (!action.endpoint || status === "pending") return;
        setStatus("pending");
        try {
          await callApi(action);
          setStatus("done");
          setTimeout(() => setStatus("idle"), 1500);
        } catch {
          setStatus("error");
          setTimeout(() => setStatus("idle"), 2500);
        }
        break;
    }
  }, [action, navigate, status]);

  const label =
    status === "pending"
      ? action.label
      : status === "done"
        ? "Done"
        : status === "error"
          ? "Failed"
          : action.label;

  return (
    <button
      onClick={handleClick}
      disabled={status === "pending"}
      aria-busy={status === "pending"}
      className={cn(
        "inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-[4px]",
        "border transition-all duration-[150ms] active:scale-[0.96]",
        status === "error"
          ? "border-mk-error/50 text-mk-error"
          : status === "done"
            ? "border-mk-success/50 text-mk-success"
            : "border-mk-accent/40 text-mk-accent hover:bg-mk-accent/10 hover:border-mk-accent/60",
        status === "pending" && "opacity-70"
      )}
    >
      {status === "pending" && <Loader2 size={12} className="animate-spin" />}
      {status === "done" && <Check size={12} />}
      {status === "error" && <XIcon size={12} />}
      {label}
    </button>
  );
}
