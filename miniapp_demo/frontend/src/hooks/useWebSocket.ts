import { useEffect, useRef, useState } from "react";

export interface UseWebSocket {
  send: (data: any) => void;
  connected: boolean;
}

/** 极简自动重连 WebSocket 钩子。onMessage 用 ref 保存,避免重连。 */
export function useWebSocket(url: string, onMessage: (data: any) => void): UseWebSocket {
  const wsRef = useRef<WebSocket | null>(null);
  const handlerRef = useRef(onMessage);
  const [connected, setConnected] = useState(false);
  handlerRef.current = onMessage;

  useEffect(() => {
    let closed = false;
    let retry: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      const ws = new WebSocket(url);
      wsRef.current = ws;
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!closed) retry = setTimeout(connect, 1000);
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (ev) => {
        try {
          handlerRef.current(JSON.parse(ev.data));
        } catch {
          /* ignore malformed */
        }
      };
    };
    connect();

    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      wsRef.current?.close();
    };
  }, [url]);

  const send = (data: any) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(data));
  };

  return { send, connected };
}
