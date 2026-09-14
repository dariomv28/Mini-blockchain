import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { NodeStatus } from "../types/api";

type WebSocketEventListener = (event: { type: string; payload?: any; [key: string]: any }) => void;
const eventListeners = new Set<WebSocketEventListener>();

export function addWebSocketListener(listener: WebSocketEventListener): () => void {
  eventListeners.add(listener);
  return () => {
    eventListeners.delete(listener);
  };
}

export function useWebSocket() {
  const queryClient = useQueryClient();
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [nodeStatus, setNodeStatus] = useState<NodeStatus | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const pingIntervalRef = useRef<number | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const lastStatusRef = useRef<{ height?: number; tip_hash?: string; pending_count?: number } | null>(null);
  const lastInvalidateTimeRef = useRef<number>(0);

  useEffect(() => {
    let unmounted = false;

    function connect() {
      if (unmounted) return;

      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const wsUrl = `${protocol}//${window.location.host}/api/v1/ws`;

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (unmounted) return;
        setIsConnected(true);

        // Send ping every 20 seconds
        if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
        pingIntervalRef.current = window.setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send("ping");
          }
        }, 20000);
      };

      ws.onmessage = (event) => {
        if (unmounted) return;
        const msg = event.data;

        if (msg === "pong") {
          return;
        }

        try {
          const parsed = JSON.parse(msg);

          // Dispatch to all registered listeners
          for (const listener of eventListeners) {
            try {
              listener(parsed);
            } catch {
              // Ignore listener error
            }
          }

          if (parsed.type === "node_status" || parsed.event === "node_status") {
            const statusData: NodeStatus = parsed.payload || parsed.data || parsed;
            setNodeStatus(statusData);

            const prev = lastStatusRef.current;
            const hasChanged =
              prev !== null &&
              (prev.height !== statusData.height ||
                prev.tip_hash !== statusData.tip_hash ||
                prev.pending_count !== statusData.pending_count);

            lastStatusRef.current = {
              height: statusData.height,
              tip_hash: statusData.tip_hash,
              pending_count: statusData.pending_count,
            };

            // Only invalidate when node/chain state actually changed
            const now = Date.now();
            if (hasChanged && now - lastInvalidateTimeRef.current >= 1500) {
              lastInvalidateTimeRef.current = now;
              queryClient.invalidateQueries({ queryKey: ["wallet"] });
              queryClient.invalidateQueries({ queryKey: ["mempool"] });
              queryClient.invalidateQueries({ queryKey: ["mining"] });
            }
          } else if (parsed.type === "block_accepted") {
            queryClient.invalidateQueries({ queryKey: ["wallet"] });
            queryClient.invalidateQueries({ queryKey: ["mempool"] });
            queryClient.invalidateQueries({ queryKey: ["mining"] });
          }
        } catch {
          // Ignore non-JSON
        }
      };

      ws.onclose = () => {
        if (unmounted) return;
        setIsConnected(false);
        if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
        // Attempt reconnect after 3 seconds
        reconnectTimeoutRef.current = window.setTimeout(connect, 3000);
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    connect();

    return () => {
      unmounted = true;
      if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [queryClient]);

  return { isConnected, nodeStatus };
}
