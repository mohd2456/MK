/**
 * streamChatMessage Tests
 * ========================
 * Verifies the SSE consumer parses `data:` frames into tokens, accumulates the
 * full reply, handles frames split across network chunks, and fires callbacks.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { streamChatMessage } from "@/lib/chat";

function sseStream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c));
      controller.close();
    },
  });
}

function mockFetch(chunks: string[]) {
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    statusText: "OK",
    body: sseStream(chunks),
  });
}

describe("streamChatMessage", () => {
  beforeEach(() => {
    localStorage.clear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("parses token frames and returns the full reply", async () => {
    global.fetch = mockFetch([
      'data: {"type":"token","content":"Hel"}\n\n',
      'data: {"type":"token","content":"lo!"}\n\n',
      'data: {"type":"done","ok":true}\n\n',
    ]) as unknown as typeof fetch;

    const tokens: string[] = [];
    let done = false;
    const full = await streamChatMessage(
      "hi",
      { page: "/" },
      { onToken: (t) => tokens.push(t), onDone: () => (done = true) }
    );

    expect(tokens).toEqual(["Hel", "lo!"]);
    expect(full).toBe("Hello!");
    expect(done).toBe(true);
  });

  it("handles SSE frames split across network chunks", async () => {
    // A single frame delivered in two byte chunks.
    global.fetch = mockFetch([
      'data: {"type":"to',
      'ken","content":"X"}\n\n',
      'data: {"type":"done","ok":true}\n\n',
    ]) as unknown as typeof fetch;

    const tokens: string[] = [];
    const full = await streamChatMessage(
      "hi",
      { page: "/" },
      { onToken: (t) => tokens.push(t) }
    );

    expect(tokens).toEqual(["X"]);
    expect(full).toBe("X");
  });

  it("invokes onError for a server-signalled error frame", async () => {
    global.fetch = mockFetch([
      'data: {"type":"error","message":"boom"}\n\n',
      'data: {"type":"done","ok":true}\n\n',
    ]) as unknown as typeof fetch;

    const errors: unknown[] = [];
    await streamChatMessage(
      "hi",
      { page: "/" },
      { onToken: () => {}, onError: (e) => errors.push(e) }
    );

    expect(errors.length).toBe(1);
  });
});
