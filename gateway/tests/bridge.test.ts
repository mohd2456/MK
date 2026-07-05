/**
 * Unit tests for the MK Bridge communication layer.
 *
 * Tests HTTP communication, retry logic, and error handling.
 */

import { describe, it, expect } from "vitest";
import { MKBridge } from "../src/bridge.js";
import type { GatewayConfig } from "../src/types.js";

const mockConfig: GatewayConfig = {
  telegramBotToken: "test-token",
  mkCoreUrl: "http://127.0.0.1:8741",
  allowedChatIds: [],
  healthPort: 3000,
  pollInterval: 5000,
};

describe("MKBridge", () => {
  it("should initialize with config", () => {
    const bridge = new MKBridge(mockConfig);
    expect(bridge).toBeDefined();
    expect(bridge.isConnected()).toBe(false);
  });

  it("should report not connected initially", () => {
    const bridge = new MKBridge(mockConfig);
    expect(bridge.isConnected()).toBe(false);
  });

  it("should handle connection failure gracefully", async () => {
    const bridge = new MKBridge({
      ...mockConfig,
      mkCoreUrl: "http://127.0.0.1:9999",
    });

    await expect(bridge.sendMessage("hello", "user1")).rejects.toThrow();
    expect(bridge.isConnected()).toBe(false);
  });

  it("should handle health check failure", async () => {
    const bridge = new MKBridge({
      ...mockConfig,
      mkCoreUrl: "http://127.0.0.1:9999",
    });

    await expect(bridge.getStatus()).rejects.toThrow();
  });

  it("should return empty array on poll failure", async () => {
    const bridge = new MKBridge({
      ...mockConfig,
      mkCoreUrl: "http://127.0.0.1:9999",
    });

    const result = await bridge.pollProactive();
    expect(result).toEqual([]);
  });
});
