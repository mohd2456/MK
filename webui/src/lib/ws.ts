/**
 * MK OS WebSocket Client
 * =======================
 * Manages WebSocket connection with:
 * - Automatic reconnection with exponential backoff
 * - Heartbeat pings to detect dead connections
 * - Typed event dispatch for chat messages and system events
 * - Connection state tracking
 */

import {
  WS_URL,
  WS_HEARTBEAT_INTERVAL,
  WS_MAX_RECONNECT_DELAY,
} from "./constants";

export type ConnectionState = "connecting" | "connected" | "disconnected";

export interface WSMessage {
  type: string;
  [key: string]: unknown;
}

type MessageHandler = (message: WSMessage) => void;
type StateHandler = (state: ConnectionState) => void;

export class MKWebSocket {
  private ws: WebSocket | null = null;
  private token: string | null = null;
  private reconnectDelay = 1000;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private missedPongs = 0;
  private intentionalClose = false;

  private messageHandlers: Set<MessageHandler> = new Set();
  private stateHandlers: Set<StateHandler> = new Set();
  private _state: ConnectionState = "disconnected";

  get state(): ConnectionState {
    return this._state;
  }

  private setState(state: ConnectionState) {
    this._state = state;
    this.stateHandlers.forEach((handler) => handler(state));
  }

  /**
   * Connect to the WebSocket server.
   */
  connect(token: string) {
    this.token = token;
    this.intentionalClose = false;
    this.createConnection();
  }

  /**
   * Disconnect and stop reconnection attempts.
   */
  disconnect() {
    this.intentionalClose = true;
    this.cleanup();
    this.setState("disconnected");
  }

  /**
   * Send a typed message through the WebSocket.
   */
  send(message: WSMessage) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  /**
   * Subscribe to incoming messages.
   */
  onMessage(handler: MessageHandler): () => void {
    this.messageHandlers.add(handler);
    return () => this.messageHandlers.delete(handler);
  }

  /**
   * Subscribe to connection state changes.
   */
  onStateChange(handler: StateHandler): () => void {
    this.stateHandlers.add(handler);
    return () => this.stateHandlers.delete(handler);
  }

  private createConnection() {
    this.cleanup();
    this.setState("connecting");

    const url = `${WS_URL}?token=${this.token}`;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.setState("connected");
      this.reconnectDelay = 1000;
      this.missedPongs = 0;
      this.startHeartbeat();
    };

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const message = JSON.parse(event.data as string) as WSMessage;

        // Handle pong responses
        if (message.type === "pong") {
          this.missedPongs = 0;
          return;
        }

        // Dispatch to handlers
        this.messageHandlers.forEach((handler) => handler(message));
      } catch {
        // Ignore malformed messages
      }
    };

    this.ws.onclose = () => {
      this.stopHeartbeat();
      if (!this.intentionalClose) {
        this.setState("disconnected");
        this.scheduleReconnect();
      }
    };

    this.ws.onerror = () => {
      // onclose will fire after onerror, handling reconnect there
    };
  }

  private startHeartbeat() {
    this.heartbeatTimer = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: "ping" }));
        this.missedPongs++;

        // Connection considered dead after 3 missed pongs
        if (this.missedPongs >= 3) {
          this.ws.close();
        }
      }
    }, WS_HEARTBEAT_INTERVAL);
  }

  private stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private scheduleReconnect() {
    this.reconnectTimer = setTimeout(() => {
      this.createConnection();
    }, this.reconnectDelay);

    // Exponential backoff: 1s, 2s, 4s, 8s, ... max 30s
    this.reconnectDelay = Math.min(
      this.reconnectDelay * 2,
      WS_MAX_RECONNECT_DELAY
    );
  }

  private cleanup() {
    this.stopHeartbeat();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onmessage = null;
      this.ws.onclose = null;
      this.ws.onerror = null;
      if (
        this.ws.readyState === WebSocket.OPEN ||
        this.ws.readyState === WebSocket.CONNECTING
      ) {
        this.ws.close();
      }
      this.ws = null;
    }
  }
}

/** Singleton WebSocket instance for the app */
export const wsClient = new MKWebSocket();
