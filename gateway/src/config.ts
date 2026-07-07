/**
 * Gateway configuration module.
 *
 * Loads configuration from environment variables.
 * Only Telegram token is required — Discord and Matrix are optional.
 * You can enable platforms one at a time.
 */

import type { GatewayConfig } from "./types.js";

/**
 * Load gateway configuration from environment variables.
 *
 * Required: TELEGRAM_BOT_TOKEN (at minimum)
 * Optional: DISCORD_BOT_TOKEN, MATRIX_* vars
 */
export function loadConfig(): GatewayConfig {
  const telegramToken = process.env.TELEGRAM_BOT_TOKEN || "";
  const discordToken = process.env.DISCORD_BOT_TOKEN || "";

  if (!telegramToken && !discordToken) {
    throw new Error(
      "At least TELEGRAM_BOT_TOKEN or DISCORD_BOT_TOKEN must be set"
    );
  }

  const allowedChatIds = process.env.ALLOWED_CHAT_IDS
    ? process.env.ALLOWED_CHAT_IDS.split(",").map((id) => id.trim())
    : [];

  const discordGuilds = process.env.DISCORD_ALLOWED_GUILDS
    ? process.env.DISCORD_ALLOWED_GUILDS.split(",").map((id) => id.trim())
    : [];

  const discordUsers = process.env.DISCORD_ALLOWED_USERS
    ? process.env.DISCORD_ALLOWED_USERS.split(",").map((id) => id.trim())
    : [];

  const matrixRooms = process.env.MATRIX_ALLOWED_ROOMS
    ? process.env.MATRIX_ALLOWED_ROOMS.split(",").map((id) => id.trim())
    : [];

  return {
    telegramBotToken: telegramToken,
    allowedChatIds,
    discordBotToken: discordToken,
    discordAllowedGuilds: discordGuilds,
    discordAllowedUsers: discordUsers,
    matrixHomeserver: process.env.MATRIX_HOMESERVER || "",
    matrixAccessToken: process.env.MATRIX_ACCESS_TOKEN || "",
    matrixUserId: process.env.MATRIX_USER_ID || "",
    matrixAllowedRooms: matrixRooms,
    mkCoreUrl: process.env.MK_CORE_URL || "http://127.0.0.1:8741",
    healthPort: parseInt(process.env.HEALTH_PORT || "3000", 10),
    pollInterval: parseInt(process.env.POLL_INTERVAL || "5000", 10),
  };
}

/**
 * Check if a chat/user ID is allowed for a platform.
 * If the allowed list is empty, all are permitted.
 */
export function isChatAllowed(chatId: string, config: GatewayConfig): boolean {
  if (config.allowedChatIds.length === 0) {
    return true;
  }
  return config.allowedChatIds.includes(chatId);
}

export function isDiscordUserAllowed(
  userId: string,
  config: GatewayConfig
): boolean {
  if (config.discordAllowedUsers.length === 0) {
    return true;
  }
  return config.discordAllowedUsers.includes(userId);
}

export function isMatrixRoomAllowed(
  roomId: string,
  config: GatewayConfig
): boolean {
  if (config.matrixAllowedRooms.length === 0) {
    return true;
  }
  return config.matrixAllowedRooms.includes(roomId);
}
