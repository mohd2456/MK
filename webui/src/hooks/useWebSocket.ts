/**
 * useWebSocket Hook
 * ==================
 * Wraps the MKWebSocket singleton, providing connection lifecycle
 * management tied to the current auth token from authStore.
 */

import { useEffect, useState, useCallback, useRef } from "react";
import { wsClient, type ConnectionState, type WSMessage } from "@/lib/ws";
import { useAuthStore } from "@/stores/authStore";

interface UseWebSocketReturn {
  /** Current connection state */
  connectionState: ConnectionState;
  /** Whether the socket is fully connected */
  isConnected: boolean;
  /** Connect (called automatically when token is available) */
  connect: () => void;
  /** Disconnect the WebSocket */
  disconnect: () => void;
  /** Send a typed message */
  send: (message: WSMessage) => void;
  /** Subscribe to messages (returns unsubscribe fn) */
  onMessage: (handler: (msg: WSMessage) => void) => () => void;
}

export function useWebSocket(): UseWebSocketReturn {
  const token = useAuthStore((s) => s.token);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const [connectionState, setConnectionState] = useState<ConnectionState>(wsClient.state);
  const connectedRef = useRef(false);

  // Track connection state changes
  useEffect(() => {
    const unsub = wsClient.onStateChange((state) => {
      setConnectionState(state);
    });
    return unsub;
  }, []);

  // Auto-connect when authenticated and token available
  useEffect(() => {
    if (isAuthenticated && token && !connectedRef.current) {
      wsClient.connect(token);
      connectedRef.current = true;
    } else if (!isAuthenticated && connectedRef.current) {
      wsClient.disconnect();
      connectedRef.current = false;
    }
  }, [isAuthenticated, token]);

  const connect = useCallback(() => {
    if (token) {
      wsClient.connect(token);
      connectedRef.current = true;
    }
  }, [token]);

  const disconnect = useCallback(() => {
    wsClient.disconnect();
    connectedRef.current = false;
  }, []);

  const send = useCallback((message: WSMessage) => {
    wsClient.send(message);
  }, []);

  const onMessage = useCallback((handler: (msg: WSMessage) => void) => {
    return wsClient.onMessage(handler);
  }, []);

  return {
    connectionState,
    isConnected: connectionState === "connected",
    connect,
    disconnect,
    send,
    onMessage,
  };
}
