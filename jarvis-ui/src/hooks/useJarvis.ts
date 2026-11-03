import { useState, useEffect, useRef, useCallback } from "react";
import { JarvisState } from "../types";

const INITIAL_STATE: JarvisState = {
  connected: false,
  expanded: false,
  statusLabel: "Ready",
  statusColor: "#a3a3a3",
  mood: "online",
  lastQuery: "",
  lastReply: "Welcome back, sir. All systems nominal.",
  isListening: false,
  isThinking: false,
  isSpeaking: false,
  hasApproval: false,
  telemetry: {
    cpu: 18,
    ram: 52,
    bat: "85% AC",
    batLevel: 85,
    charging: true,
  },
};

export function useJarvis(wsUrl: string = "ws://127.0.0.1:8765") {
  const [state, setState] = useState<JarvisState>(INITIAL_STATE);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number>();

  const connect = useCallback(() => {
    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setState((prev) => ({ ...prev, connected: true }));
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "state_update") {
            setState((prev) => ({
              ...prev,
              ...data.payload,
              expanded: prev.expanded, // Keep user's expanded UI state
              connected: true,
            }));
          }
        } catch {
          // ignore malformed frame
        }
      };

      ws.onclose = () => {
        setState((prev) => ({ ...prev, connected: false }));
        reconnectTimeoutRef.current = window.setTimeout(connect, 2000);
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      reconnectTimeoutRef.current = window.setTimeout(connect, 2000);
    }
  }, [wsUrl]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [connect]);

  const sendQuery = useCallback((query: string) => {
    if (!query.trim()) return;
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "query", text: query }));
    }
    setState((prev) => ({
      ...prev,
      lastQuery: query,
      statusLabel: "Thinking",
      statusColor: "#f59e0b",
      mood: "thinking",
      isThinking: true,
      lastReply: `Processing '${query}'...`,
    }));
  }, []);

  const toggleMic = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "mic_click" }));
    }
  }, []);

  const stopSpeech = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "stop_speech" }));
    }
    setState((prev) => ({ ...prev, isSpeaking: false, statusLabel: "Ready", statusColor: "#a3a3a3", mood: "online" }));
  }, []);

  const respondApproval = useCallback((accepted: boolean) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "approval", accepted }));
    }
    setState((prev) => ({ ...prev, hasApproval: false, isSpeaking: false }));
  }, []);

  const setExpanded = useCallback((expanded: boolean) => {
    setState((prev) => ({ ...prev, expanded }));
  }, []);

  return {
    state,
    sendQuery,
    toggleMic,
    stopSpeech,
    respondApproval,
    setExpanded,
  };
}
