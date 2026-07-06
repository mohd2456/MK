/**
 * Bridge to MK Core Engine.
 *
 * HTTP client that communicates with MK's internal API.
 * Supports both natural language messages and direct server commands.
 */

import type {
  GatewayConfig,
  HealthStatus,
  MessageRequest,
  MessageResponseBody,
  ProactiveMessage,
} from "./types.js";

/**
 * Bridge class for communicating with MK Core via HTTP.
 */
export class MKBridge {
  private readonly baseUrl: string;
  private readonly timeout: number;
  private readonly maxRetries: number;
  private connected: boolean = false;

  constructor(config: GatewayConfig) {
    this.baseUrl = config.mkCoreUrl;
    this.timeout = 60000; // 60s for long operations
    this.maxRetries = 3;
  }

  /**
   * Send a natural language message to MK core.
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

    const response = await this.fetchWithRetry(`${this.baseUrl}/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });

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
   * Send a direct server management command to MK core.
   * Bypasses the LLM — goes straight to the server tool.
   */
  async sendServerCommand(
    domain: string,
    action: string,
    args: Record<string, unknown>
  ): Promise<{ text: string; metadata?: Record<string, unknown> }> {
    const response = await this.fetchWithRetry(`${this.baseUrl}/server`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domain, action, args }),
    });

    if (!response.ok) {
      throw new Error(
        `Server command failed (${response.status}): ${await response.text()}`
      );
    }

    const data = await response.json();
    this.connected = true;
    return data as { text: string; metadata?: Record<string, unknown> };
  }

  /**
   * Check MK core health status.
   */
  async getStatus(): Promise<HealthStatus> {
    const response = await this.fetchWithRetry(`${this.baseUrl}/health`, {
      method: "GET",
    });

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
   */
  async pollProactive(
    platform: string = "telegram"
  ): Promise<ProactiveMessage[]> {
    try {
      const response = await this.fetchWithRetry(
        `${this.baseUrl}/proactive?platform=${platform}`,
        { method: "GET" }
      );
      if (!response.ok) return [];
      return (await response.json()) as ProactiveMessage[];
    } catch {
      return [];
    }
  }

  isConnected(): boolean {
    return this.connected;
  }

  private async fetchWithRetry(
    url: string,
    options: RequestInit,
    retries: number = this.maxRetries
  ): Promise<Response> {
    let lastError: Error | null = null;

    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), this.timeout);

        const response = await fetch(url, {
          ...options,
          signal: controller.signal,
        });

        clearTimeout(timeoutId);
        return response;
      } catch (error) {
        lastError = error as Error;
        if (attempt < retries) {
          await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)));
        }
      }
    }

    this.connected = false;
    throw new Error(
      `Failed to reach MK core after ${retries + 1} attempts: ${lastError?.message}`
    );
  }
}
