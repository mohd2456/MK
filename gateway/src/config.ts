/**
 * Gateway configuration module.
 *
 * Loads configuration from environment variables with sensible defaults.
 * Required variables: TELEGRAM_BOT_TOKEN
 */

import { z } from "zod";
import type { GatewayConfig } from "./types.js";

/** Zod schema for validating environment configuration. */
const configSchema = z.object({
  telegramBotToken: z.string().min(1, "TELEGRAM_BOT_TOKEN is required"),
  mkCoreUrl: z.string().url().default("http://127.0.0.1:8741"),
  allowedChatIds: z.array(z.string()).default([]),
  healthPort: z.number().int().positive().default(3000),
  pollInterval: z.number().int().positive().default(5000),
});

/**
 * Load and validate gateway configuration from environment variables.
 *
 * @returns Validated GatewayConfig object
 * @throws Error if required variables are missing
 */
export function loadConfig(): GatewayConfig {
  const allowedIds = process.env.ALLOWED_CHAT_IDS
    ? process.env.ALLOWED_CHAT_IDS.split(",").map((id) => id.trim())
    : [];

  const raw = {
    telegramBotToken: process.env.TELEGRAM_BOT_TOKEN || "",
    mkCoreUrl: process.env.MK_CORE_URL || "http://127.0.0.1:8741",
    allowedChatIds: allowedIds,
    healthPort: parseInt(process.env.HEALTH_PORT || "3000", 10),
    pollInterval: parseInt(process.env.POLL_INTERVAL || "5000", 10),
  };

  const result = configSchema.safeParse(raw);

  if (!result.success) {
    const errors = result.error.issues
      .map((i) => `${i.path.join(".")}: ${i.message}`)
      .join(", ");
    throw new Error(`Gateway configuration error: ${errors}`);
  }

  return result.data;
}

/**
 * Check if a chat ID is in the allowed list.
 * If the allowed list is empty, all chats are permitted.
 *
 * @param chatId - The chat ID to check
 * @param config - Gateway configuration
 * @returns true if the chat is allowed
 */
export function isChatAllowed(chatId: string, config: GatewayConfig): boolean {
  if (config.allowedChatIds.length === 0) {
    return true;
  }
  return config.allowedChatIds.includes(chatId);
}
