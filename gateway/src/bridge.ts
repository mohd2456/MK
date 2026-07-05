/**
 * Bridge to MK Core Engine.
 *
 * HTTP client that communicates with MK's internal API.
 * Handles connection management, retries, and error handling.
 */

import type {
  GatewayConfig,
  HealthStatus,
  MessageRequest,
  MessageResponseBody,
  ProactiveMessage,
} from "./types.js";

/** Options for the bridge HTTP client. */
interface BridgeOptions {
  baseUrl: string;
  timeout: number;
  maxRetries: number;
  retryDelay: number;
}

/**
 * Bridge class for communicating with MK Core via HTTP.
 *
 * Provides methods for sending messages, checking health,
 * and polling for proactive messages. Includes automatic
 * retry logic for transient failures.
 */
export class MKBridge {
  private readonly options: BridgeOptions;
  private connected: boolean = false;

  constructor(config: GatewayConfig) {
    this.options = {
      baseUrl: config.mkCoreUrl,
      timeout: 30000,
      maxRetries: 3,
      retryDelay: 1000,
    };
  }

  /**
   * Send a message to MK core and get a response.
   *
   * @param text - User message text
   * @param senderId - Sender identifier
   * @param platform - Source platform name
   * @returns MK's response text
   */
  async sendMessage(
    text: string,
    senderId: string,
    platform: string = "telegram"
  ): Promise<MessageResponseBody> {
    const request: MessageRequest = {
      text,
      sender_id: senderId,
      platform,
    };

    const response = await this.fetchWithRetry(
      `${this.options.baseUrl}/message`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      }
    );

    if (!response.ok) {
      throw new Error(
        `MK core returned ${response.status}: ${await response.text()}`
      );
    }

    const data = (await response.json()) as MessageResponseBody;
    this.connected = true;
    return data;
  }

  /**
   * Check MK core health status.
   *
   * @returns Health status from MK core
   */
  async getStatus(): Promise<HealthStatus> {
    const response = await this.fetchWithRetry(
      `${this.options.baseUrl}/health`,
      { method: "GET" }
    );

    if (!response.ok) {
      this.connected = false;
      throw new Error(`Health check failed: ${response.status}`);
    }

    const data = (await response.json()) as HealthStatus;
    this.connected = true;
    return data;
  }

  /**
   * Poll for proactive messages from MK core.
   *
   * @param platform - Platform to poll for
   * @returns Array of pending proactive messages
   */
  async pollProactive(platform: string = "telegram"): Promise<ProactiveMessage[]> {
    try {
      const response = await this.fetchWithRetry(
        `${this.options.baseUrl}/proactive?platform=${platform}`,
        { method: "GET" }
      );

      if (!response.ok) {
        return [];
      }

      return (await response.json()) as ProactiveMessage[];
    } catch {
      return [];
    }
  }

  /**
   * Check if the bridge is currently connected to MK core.
   */
  isConnected(): boolean {
    return this.connected;
  }

  /**
   * Fetch with automatic retry on failure.
   */
  private async fetchWithRetry(
    url: string,
    options: RequestInit,
    retries: number = this.options.maxRetries
  ): Promise<Response> {
    let lastError: Error | null = null;

    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(
          () => controller.abort(),
          this.options.timeout
        );

        const response = await fetch(url, {
          ...options,
          signal: controller.signal,
        });

        clearTimeout(timeoutId);
        return response;
      } catch (error) {
        lastError = error as Error;
        if (attempt < retries) {
          await this.sleep(this.options.retryDelay * (attempt + 1));
        }
      }
    }

    this.connected = false;
    throw new Error(
      `Failed to connect to MK core after ${retries + 1} attempts: ${lastError?.message}`
    );
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}
