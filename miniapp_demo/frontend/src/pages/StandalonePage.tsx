import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { HostBridge } from "../host/bridge";
import { useWebSocket } from "../hooks/useWebSocket";
import { ensureMicPermission } from "../host/permissions";
import type { AppManifest } from "../types";

type Device = "desktop" | "mobile";

const WS_URL = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;

function detectDevice(): Device {
  if (typeof navigator !== "undefined" && /Mobi|Android|iPhone|iPad|iPod/i.test(navigator.userAgent)) {
    return "mobile";
  }
  return window.innerWidth <= 768 ? "mobile" : "desktop";
}

export function StandalonePage() {
  const { appId } = useParams<{ appId: string }>();
  const [searchParams] = useSearchParams();
  const [manifest, setManifest] = useState<AppManifest | null>(null);
  const [error, setError] = useState<string | null>(null);

  const device: Device = (searchParams.get("device") as Device) || detectDevice();

  const sendRef = useRef<(f: any) => void>(() => {});
  const bridgeRef = useRef<HostBridge | null>(null);

  const onDown = useCallback((data: any) => {
    bridgeRef.current?.handleDownFrame(data);
  }, []);

  const ws = useWebSocket(WS_URL, onDown);
  sendRef.current = ws.send;

  if (!bridgeRef.current) {
    bridgeRef.current = new HostBridge(
      (frame) => sendRef.current(frame),
      () => {},
    );
  }

  useEffect(() => {
    if (!appId) return;
    bridgeRef.current?.setApp(appId);
    return () => {
      bridgeRef.current?.setApp(null);
      bridgeRef.current?.setIframe(null);
    };
  }, [appId]);

  useEffect(() => {
    if (!appId) return;
    fetch(`/api/apps/${appId}/reset-session`, { method: "POST" })
      .then(() => api.manifest(appId))
      .then(setManifest)
      .catch(() => setError(`小程序 "${appId}" 不存在`));
  }, [appId]);

  const needsMic = !!manifest?.permissions?.includes("microphone");
  useEffect(() => {
    if (needsMic) void ensureMicPermission();
  }, [needsMic]);
  const allow = needsMic ? "microphone" : undefined;

  const src = useMemo(() => {
    if (!manifest || !appId) return null;
    const entries = manifest.entries;
    let file = entries?.default || "index.html";
    if (device === "mobile" && entries?.mobile) file = entries.mobile;
    if (device === "desktop" && entries?.desktop) file = entries.desktop;
    return `/api/apps/${appId}/ui/${file}?device=${device}`;
  }, [appId, manifest, device]);

  if (!appId) return null;

  if (error) {
    return (
      <div style={styles.center}>
        <span style={{ color: "#aaa" }}>{error}</span>
      </div>
    );
  }

  if (!src) {
    return (
      <div style={styles.center}>
        <span style={{ color: "#666", fontSize: 14 }}>加载中…</span>
      </div>
    );
  }

  return (
    <div style={styles.root}>
      <iframe
        ref={(el) => bridgeRef.current?.setIframe(el)}
        src={src}
        title={manifest?.name || appId}
        allow={allow}
        style={styles.iframe}
      />
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  root: {
    position: "fixed", inset: 0,
    overflow: "hidden",
    background: "#0a0718",
    fontFamily: '"PingFang SC", "Songti SC", system-ui, sans-serif',
  },
  center: {
    display: "flex", alignItems: "center", justifyContent: "center",
    height: "100vh", background: "#0a0718",
    fontFamily: "system-ui, sans-serif", fontSize: 16,
  },
  iframe: {
    position: "absolute", inset: 0,
    width: "100%", height: "100%",
    border: "none", margin: 0, padding: 0,
  },
};
