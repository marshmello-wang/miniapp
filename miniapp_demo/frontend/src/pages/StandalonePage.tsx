import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { HostBridge } from "../host/bridge";
import { useWebSocket } from "../hooks/useWebSocket";
import { ensureMicPermission } from "../host/permissions";
import type { AppManifest } from "../types";

type Device = "desktop" | "mobile";
interface HistoryMsg { role: string; content: string }

const WS_URL = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;

function detectDevice(): Device {
  if (typeof navigator !== "undefined" && /Mobi|Android|iPhone|iPad|iPod/i.test(navigator.userAgent)) {
    return "mobile";
  }
  return window.innerWidth <= 768 ? "mobile" : "desktop";
}

const PULL_THRESHOLD = 80;

function HistoryPanel({ appId, appName, visible }: { appId: string; appName: string; visible: boolean }) {
  const [msgs, setMsgs] = useState<HistoryMsg[]>([]);
  const [loaded, setLoaded] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!visible || loaded) return;
    fetch(`/api/apps/${appId}/history`)
      .then((r) => r.json())
      .then((data: HistoryMsg[]) => { setMsgs(data); setLoaded(true); })
      .catch(() => setLoaded(true));
  }, [appId, visible, loaded]);

  useEffect(() => {
    if (visible) setLoaded(false);
  }, [visible]);

  useEffect(() => {
    if (visible && loaded) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [visible, loaded]);

  if (!visible) return null;

  return (
    <div style={styles.historyPanel}>
      <div style={styles.historyTitle}>对话记录</div>
      {msgs.length === 0 ? (
        <div style={styles.historyEmpty}>暂无对话记录</div>
      ) : (
        <div style={styles.historyList}>
          {msgs.map((m, i) => (
            <div key={i} style={styles.msgItem}>
              <div style={styles.msgRole}>
                <span style={m.role === "user" ? styles.roleUser : styles.roleAi}>
                  {m.role === "user" ? "你" : appName}
                </span>
              </div>
              <div style={styles.msgText}>{m.content}</div>
              {i < msgs.length - 1 && <div style={styles.msgDivider} />}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  );
}

export function StandalonePage() {
  const { appId } = useParams<{ appId: string }>();
  const [searchParams] = useSearchParams();
  const [manifest, setManifest] = useState<AppManifest | null>(null);
  const [error, setError] = useState<string | null>(null);

  const device: Device = (searchParams.get("device") as Device) || detectDevice();

  // pull-down state
  const [pullY, setPullY] = useState(0);
  const [historyOpen, setHistoryOpen] = useState(false);
  const touchStartRef = useRef<{ y: number; active: boolean }>({ y: 0, active: false });

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

  const onTouchStart = useCallback((e: React.TouchEvent) => {
    if (historyOpen) return;
    touchStartRef.current = { y: e.touches[0].clientY, active: true };
  }, [historyOpen]);

  const onTouchMove = useCallback((e: React.TouchEvent) => {
    if (!touchStartRef.current.active || historyOpen) return;
    const dy = e.touches[0].clientY - touchStartRef.current.y;
    if (dy > 0) {
      e.preventDefault();
      setPullY(Math.min(dy * 0.5, 160));
    }
  }, [historyOpen]);

  const onTouchEnd = useCallback(() => {
    if (!touchStartRef.current.active) return;
    touchStartRef.current.active = false;
    if (pullY >= PULL_THRESHOLD) {
      setHistoryOpen(true);
    }
    setPullY(0);
  }, [pullY]);

  // 鼠标下拉（桌面端）
  const onMouseDown = useCallback((e: React.MouseEvent) => {
    if (historyOpen) return;
    touchStartRef.current = { y: e.clientY, active: true };
    const onMouseMove = (ev: MouseEvent) => {
      if (!touchStartRef.current.active) return;
      const dy = ev.clientY - touchStartRef.current.y;
      if (dy > 0) setPullY(Math.min(dy * 0.5, 160));
    };
    const onMouseUp = () => {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
      if (!touchStartRef.current.active) return;
      touchStartRef.current.active = false;
      setPullY((cur) => {
        if (cur >= PULL_THRESHOLD) setHistoryOpen(true);
        return 0;
      });
    };
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  }, [historyOpen]);

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
      {/* 顶部触摸/鼠标捕获区域（覆盖在 iframe 上方） */}
      {!historyOpen && (
        <div
          style={styles.pullZone}
          onTouchStart={onTouchStart}
          onTouchMove={onTouchMove}
          onTouchEnd={onTouchEnd}
          onMouseDown={onMouseDown}
        >
          <div style={styles.topHandleBar} />
          <span style={styles.topHandleText}>↓ 下拉查看对话记录</span>
        </div>
      )}

      {/* pull indicator */}
      {!historyOpen && pullY > 0 && (
        <div style={{
          ...styles.pullIndicator,
          opacity: Math.min(pullY / PULL_THRESHOLD, 1),
          transform: `translateY(${pullY - 10}px)`,
        }}>
          <span>{pullY >= PULL_THRESHOLD ? "松开查看历史" : "继续下拉…"}</span>
        </div>
      )}

      {/* history overlay */}
      {historyOpen && (
        <div style={styles.historyOverlay}>
          <HistoryPanel appId={appId} appName={manifest?.name || appId} visible={historyOpen} />
          <button
            style={styles.historyClose}
            onClick={() => setHistoryOpen(false)}
          >
            收起历史 ↑
          </button>
        </div>
      )}

      <iframe
        ref={(el) => bridgeRef.current?.setIframe(el)}
        src={src}
        title={manifest?.name || appId}
        allow={allow}
        style={{
          ...styles.iframe,
          transform: historyOpen ? "translateY(100vh)" : `translateY(${pullY * 0.3}px)`,
          transition: pullY === 0 ? "transform 0.3s ease" : "none",
          pointerEvents: historyOpen ? "none" : "auto",
        }}
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

  pullZone: {
    position: "absolute", top: 0, left: 0, right: 0,
    zIndex: 10,
    height: 32,
    display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 3,
    cursor: "grab",
    background: "linear-gradient(180deg, rgba(10,7,24,0.6) 0%, transparent 100%)",
    userSelect: "none" as const,
    touchAction: "none" as const,
  },
  topHandleBar: {
    width: 36, height: 3, borderRadius: 2,
    background: "rgba(201,182,255,0.25)",
  },
  topHandleText: {
    fontSize: 10, color: "rgba(154,147,199,0.5)", letterSpacing: "0.1em",
  },

  pullIndicator: {
    position: "absolute", top: 32, left: 0, right: 0,
    zIndex: 10,
    display: "flex", alignItems: "center", justifyContent: "center",
    color: "#9a93c7", fontSize: 13, letterSpacing: "0.1em",
    pointerEvents: "none",
  },

  historyOverlay: {
    position: "absolute", inset: 0,
    zIndex: 20,
    display: "flex", flexDirection: "column",
    background: "linear-gradient(180deg, #0a0718 0%, #170f34 100%)",
    animation: "slideDown 0.3s ease",
  },
  historyClose: {
    flexShrink: 0,
    padding: "14px 0",
    background: "rgba(124,92,255,0.1)",
    border: "none",
    borderTop: "1px solid rgba(201,182,255,0.12)",
    color: "#9a93c7", fontSize: 14, letterSpacing: "0.12em",
    cursor: "pointer",
  },

  historyPanel: {
    flex: 1,
    overflow: "auto",
    padding: "20px 16px",
  },
  historyTitle: {
    textAlign: "center" as const,
    color: "#9a93c7", fontSize: 13, letterSpacing: "0.2em",
    marginBottom: 20,
    textTransform: "uppercase" as const,
  },
  historyEmpty: {
    textAlign: "center" as const,
    color: "#5a5380", fontSize: 14,
    padding: "60px 0",
  },
  historyList: {
    display: "flex", flexDirection: "column" as const,
    maxWidth: 600, margin: "0 auto",
  },
  msgItem: {
    padding: "16px 0",
  },
  msgRole: {
    fontSize: 12, letterSpacing: "0.1em",
    marginBottom: 6,
  },
  roleUser: {
    color: "#7c5cff",
  },
  roleAi: {
    color: "#e9c979",
  },
  msgText: {
    fontSize: 15, lineHeight: 1.8,
    color: "rgba(236,231,255,0.85)",
    whiteSpace: "pre-wrap" as const,
    wordBreak: "break-word" as const,
  },
  msgDivider: {
    height: 1, marginTop: 16,
    background: "linear-gradient(90deg, transparent, rgba(201,182,255,0.12) 20%, rgba(201,182,255,0.12) 80%, transparent)",
  },
};
