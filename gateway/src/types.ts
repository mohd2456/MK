/**
 * Type definitions for the MK Gateway.
 *
 * Defines message structures, configuration types, and
 * API request/response shapes for gateway-core communication.
 */

/** Incoming message from a user via Telegram or other platform. */
export interface IncomingMessage {
  text: string;
  senderId: string;
  platform: "telegram" | "terminal";
  timestamp: number;
  metadata?: Record<string, unknown>;
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

/** Gateway configuration shape. */
export interface GatewayConfig {
  telegramBotToken: string;
  mkCoreUrl: string;
  allowedChatIds: string[];
  healthPort: number;
  pollInterval: number;
}
