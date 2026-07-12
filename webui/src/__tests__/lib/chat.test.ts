/**
 * Chat API helpers Tests
 * =======================
 * Verifies session-id persistence, suggestion key building, and that the
 * typed helpers call the shared api client with the right shapes.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

const post = vi.fn();
const get = vi.fn();
vi.mock("@/lib/api", () => ({
  post: (...args: unknown[]) => post(...args),
  get: (...args: unknown[]) => get(...args),
}));

import {
  getChatSessionId,
  suggestionsKey,
  sendChatMessage,
  fetchSuggestions,
  fetchChatHistory,
} from "@/lib/chat";

describe("chat api helpers", () => {
  beforeEach(() => {
    post.mockReset();
    get.mockReset();
    localStorage.clear();
  });

  it("creates and persists a stable session id", () => {
    const id1 = getChatSessionId();
    const id2 = getChatSessionId();
    expect(id1).toBeTruthy();
    expect(id1).toBe(id2);
    expect(localStorage.getItem("mk_chat_session_id")).toBe(id1);
  });

  it("builds a suggestions key with page and optional selection", () => {
    expect(suggestionsKey("/storage")).toBe("/chat/suggestions?page=%2Fstorage");
    expect(suggestionsKey("/apps", "plex")).toBe(
      "/chat/suggestions?page=%2Fapps&selection=plex"
    );
  });

  it("sends a chat message with content, context, and session id", async () => {
    post.mockResolvedValue({ ok: true, content: "hi" });
    await sendChatMessage("status", { page: "/dashboard" }, "sess-1");
    expect(post).toHaveBeenCalledWith("/chat/message", {
      content: "status",
      context: { page: "/dashboard" },
      session_id: "sess-1",
    });
  });

  it("fetches suggestions via the built key", async () => {
    get.mockResolvedValue({ page: "/network", suggestions: [] });
    await fetchSuggestions("/network");
    expect(get).toHaveBeenCalledWith("/chat/suggestions?page=%2Fnetwork");
  });

  it("fetches history for a session", async () => {
    get.mockResolvedValue({ messages: [] });
    await fetchChatHistory("sess-9");
    expect(get).toHaveBeenCalledWith("/chat/history?session_id=sess-9");
  });
});
