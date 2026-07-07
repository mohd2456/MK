/**
 * Type definitions for the MK Gateway.
 *
 * Supports multiple messaging platforms:
 * - Telegram (primary)
 * - Discord
 * - Matrix (bridges to WhatsApp, Signal, iMessage via mautrix)
 */

/** Supported messaging platforms. */
export type Platform = "telegram" | "discord" | "matrix" | "terminal";

/** Incoming message from any platform. */
export interface IncomingMessage {
  text: string;
  senderId: string;
  platform: Platform;
  timestamp: number;
  replyToId?: string;
  attachments?: Attachment[];
  metadata?: Record<string, unknown>;
}

/** File/media attachment. */
export interface Attachment {
  type: "image" | "file" | "audio" | "video";
  url: string;
  filename?: string;
  mimeType?: string;
  size?: number;
}

/** Response from MK core engine. */
export interface MKResponse {
  text: string;
  senderId: string;
  metadata?: Record<string, unknown>;
}

/** Request body for the /message endpoint on MK core. */
export interface MessageRequest {
  text: string;
  sender_id: string;
  platform: string;
  reply_to?: string;
  metadata?: Record<string, unknown>;
}

/** Response body from the /message endpoint. */
export interface MessageResponseBody {
  text: string;
  sender_id: string;
  metadata?: Record<string, unknown>;
}

/** Health check response from MK core. */
export interface HealthStatus {
  status: "healthy" | "degraded" | "down";
  version: string;
  uptime_seconds: number;
}

/** Proactive message to be sent to a user. */
export interface ProactiveMessage {
  text: string;
  target_id: string;
  platform: string;
  priority: "low" | "normal" | "high";
  queued_at?: number;
}

/** Gateway configuration. */
export interface GatewayConfig {
  // Telegram
  telegramBotToken: string;
  allowedChatIds: string[];

  // Discord
  discordBotToken: string;
  discordAllowedGuilds: string[];
  discordAllowedUsers: string[];

  // Matrix (bridges WhatsApp, Signal, etc.)
  matrixHomeserver: string;
  matrixAccessToken: string;
  matrixUserId: string;
  matrixAllowedRooms: string[];

  // Core connection
  mkCoreUrl: string;
  healthPort: number;
  pollInterval: number;
}

/** Bot command definition. */
export interface BotCommand {
  command: string;
  description: string;
  handler: string;
}

/** Platform-specific message options. */
export interface SendOptions {
  parseMode?: "Markdown" | "HTML";
  replyToId?: string;
  silent?: boolean;
}
