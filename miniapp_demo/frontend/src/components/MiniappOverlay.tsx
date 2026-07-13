import { useLayoutEffect, useRef, useState } from "react";
import { HostBridge } from "../host/bridge";
import { DebugPanel } from "./DebugPanel";
import type { DebugFrame } from "../types";

interface Props {
  appId: string;
  sessionId: string;
  onClose: () => void;
}

export function MiniappOverlay({ appId, sessionId, onClose }: Props) {
  const [showDebug, setShowDebug] = useState(false);
  const [frames, setFrames] = useState<DebugFrame[]>([]);

  const iframeRef = useRef<HTMLIFrameElement>(null);

  useLayoutEffect(() => {
    const bridge = new HostBridge((f) =>
      setFrames((prev) => [...prev, f]),
    );
    bridge.setApp(appId, sessionId);
    bridge.setIframe(iframeRef.current);
    return () => bridge.dispose();
  }, [appId, sessionId]);

  const uiUrl = `/api/apps/${appId}/ui/index.html?sessionId=${encodeURIComponent(sessionId)}`;

  return (
    <div style={styles.overlay}>
      <iframe
        ref={iframeRef}
        src={uiUrl}
        style={styles.iframe}
        allow="microphone"
      />
      <button
        style={{
          ...styles.cornerBtn,
          left: 12,
          background: showDebug ? "rgba(99,102,241,0.7)" : "rgba(0,0,0,0.45)",
        }}
        onClick={() => setShowDebug((v) => !v)}
        title="Debug"
      >
        ◇
      </button>
      <button
        style={{ ...styles.cornerBtn, right: 12 }}
        onClick={onClose}
        title="关闭"
      >
        ✕
      </button>
      {showDebug && (
        <div style={styles.debugPanel}>
          <div style={styles.debugHeader}>
            <span style={styles.debugTitle}>通信调试</span>
            <button style={styles.debugClearBtn} onClick={() => setFrames([])}>
              清空
            </button>
          </div>
          <div style={styles.debugBody}>
            <DebugPanel frames={frames} />
          </div>
        </div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  overlay: {
    position: "fixed", inset: 0, zIndex: 9999,
    background: "#000",
  },
  iframe: {
    position: "absolute", inset: 0,
    width: "100%", height: "100%",
    border: "none",
  },
  cornerBtn: {
    position: "absolute", top: 12, zIndex: 2,
    width: 36, height: 36,
    borderRadius: "50%",
    border: "none",
    background: "rgba(0,0,0,0.45)",
    color: "#fff",
    fontSize: 16,
    cursor: "pointer",
    display: "flex", alignItems: "center", justifyContent: "center",
    backdropFilter: "blur(8px)",
    transition: "background 0.15s",
  },
  debugPanel: {
    position: "absolute",
    top: 56, left: 12, bottom: 12,
    width: 380,
    zIndex: 3,
    background: "rgba(11,16,32,0.92)",
    borderRadius: 14,
    display: "flex", flexDirection: "column",
    overflow: "hidden",
    backdropFilter: "blur(12px)",
    boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
  },
  debugHeader: {
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "12px 16px",
    borderBottom: "1px solid rgba(255,255,255,0.1)",
  },
  debugTitle: {
    color: "#fff", fontSize: 13, fontWeight: 600,
  },
  debugClearBtn: {
    background: "rgba(255,255,255,0.1)",
    border: "none", borderRadius: 6,
    color: "#aaa", fontSize: 12,
    padding: "4px 10px", cursor: "pointer",
  },
  debugBody: {
    flex: 1, overflow: "auto", padding: "8px 0",
  },
};
