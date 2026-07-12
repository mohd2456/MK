/**
 * ActionButton Tests
 * ===================
 * Verifies inline chat actions actually do something: api_call fires the
 * shared client (previously a silent no-op), navigate routes, and endpoint
 * normalization strips a redundant API_BASE prefix.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@/test/utils";
import { ActionButton } from "@/components/chat/ActionButton";
import type { ChatAction } from "@/types/chat";

const post = vi.fn();
const get = vi.fn();
const put = vi.fn();
const del = vi.fn();
vi.mock("@/lib/api", () => ({
  post: (...a: unknown[]) => post(...a),
  get: (...a: unknown[]) => get(...a),
  put: (...a: unknown[]) => put(...a),
  del: (...a: unknown[]) => del(...a),
}));

const navigate = vi.fn();
vi.mock("react-router-dom", async (orig) => {
  const actual = (await orig()) as Record<string, unknown>;
  return { ...actual, useNavigate: () => navigate };
});

describe("ActionButton", () => {
  beforeEach(() => {
    post.mockReset().mockResolvedValue({});
    get.mockReset().mockResolvedValue({});
    put.mockReset();
    del.mockReset();
    navigate.mockReset();
  });

  it("fires an api_call via the client (POST by default)", async () => {
    const action: ChatAction = {
      label: "Restart plex",
      action: "api_call",
      method: "POST",
      endpoint: "/apps/containers/plex/restart",
    };
    render(<ActionButton action={action} />);
    fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/apps/containers/plex/restart", undefined));
    await waitFor(() => expect(screen.getByRole("button")).toHaveTextContent("Done"));
  });

  it("normalizes an endpoint that includes the API_BASE prefix", async () => {
    const action: ChatAction = {
      label: "Run job",
      action: "api_call",
      method: "POST",
      endpoint: "/api/v1/protection/jobs/1/run",
    };
    render(<ActionButton action={action} />);
    fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/protection/jobs/1/run", undefined));
  });

  it("shows Failed when the api_call rejects", async () => {
    post.mockRejectedValueOnce(new Error("boom"));
    const action: ChatAction = {
      label: "Do it",
      action: "api_call",
      endpoint: "/x",
    };
    render(<ActionButton action={action} />);
    fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(screen.getByRole("button")).toHaveTextContent("Failed"));
  });

  it("navigates for a navigate action without calling the API", () => {
    const action: ChatAction = { label: "Go", action: "navigate", target: "/storage" };
    render(<ActionButton action={action} />);
    fireEvent.click(screen.getByRole("button"));
    expect(navigate).toHaveBeenCalledWith("/storage");
    expect(post).not.toHaveBeenCalled();
  });
});
