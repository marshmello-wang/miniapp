import { forwardRef, useImperativeHandle, useLayoutEffect, useRef, useState } from "react";
import { HostBridge } from "../host/bridge";
import { DebugPanel } from "./DebugPanel";
import type { DebugFrame, DownFrame } from "../types";

export interface MiniappOverlayHandle {
  injectDown: (frame: DownFrame) => void;
}

interface Props {
  appId: string;
  sessionId: string;
  onClose: () => void;
  mode?: "panel" | "fullscreen";
  narration?: string;
}

export const MiniappOverlay = forwardRef<MiniappOverlayHandle, Props>(function MiniappOverlay({ appId, sessionId, onClose, mode = "fullscreen", narration }, ref) {
  const [showDebug, setShowDebug] = useState(false);
  const [frames, setFrames] = useState<DebugFrame[]>([]);

  const iframeRef = useRef<HTMLIFrameElement>(null);
  const bridgeRef = useRef<HostBridge | null>(null);

  useImperativeHandle(ref, () => ({
    injectDown: (frame: DownFrame) => bridgeRef.current?.injectDown(frame),
  }));

  useLayoutEffect(() => {
    const bridge = new HostBridge((f) =>
      setFrames((prev) => [...prev, f]),
    );
    bridgeRef.current = bridge;
    bridge.setApp(appId, sessionId);
    bridge.setIframe(iframeRef.current);
    return () => { bridge.dispose(); bridgeRef.current = null; };
  }, [appId, sessionId]);

  const uiUrl = `/api/apps/${appId}/ui/index.html?sessionId=${encodeURIComponent(sessionId)}${narration ? `&narration=${encodeURIComponent(narration)}` : ""}`;

  const isPanel = mode === "panel";
  const containerStyle = isPanel ? panelStyles.container : fullscreenStyles.container;
  const iframeStyle = isPanel ? panelStyles.iframe : fullscreenStyles.iframe;

  return (
    <div style={containerStyle}>
      {isPanel && (
        <div style={panelStyles.toolbar}>
          <button
            style={{
              ...panelStyles.toolBtn,
              background: showDebug ? "rgba(99,102,241,0.15)" : "transparent",
              color: showDebug ? "#667eea" : "#888",
            }}
            onClick={() => setShowDebug((v) => !v)}
            title="Debug"
          >
            ◇
          </button>
          <button style={panelStyles.toolBtn} onClick={onClose} title="关闭">
            ✕
          </button>
        </div>
      )}
      <iframe
        ref={iframeRef}
        src={uiUrl}
        style={iframeStyle}
        allow="microphone"
      />
      {!isPanel && (
        <>
          <button
            style={{
              ...fullscreenStyles.cornerBtn,
              left: 12,
              background: showDebug ? "rgba(99,102,241,0.7)" : "rgba(0,0,0,0.45)",
            }}
            onClick={() => setShowDebug((v) => !v)}
            title="Debug"
          >
            ◇
          </button>
          <button
            style={{ ...fullscreenStyles.cornerBtn, right: 12 }}
            onClick={onClose}
            title="关闭"
          >
            ✕
          </button>
        </>
      )}
      {showDebug && (
        <div style={isPanel ? panelStyles.debugPanel : fullscreenStyles.debugPanel}>
          <div style={sharedStyles.debugHeader}>
            <span style={sharedStyles.debugTitle}>通信调试</span>
            <button style={sharedStyles.debugClearBtn} onClick={() => setFrames([])}>
              清空
            </button>
          </div>
          <div style={sharedStyles.debugBody}>
            <DebugPanel frames={frames} />
          </div>
        </div>
      )}
    </div>
  );
});

const sharedStyles: Record<string, React.CSSProperties> = {
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

const panelStyles: Record<string, React.CSSProperties> = {
  container: {
    display: "flex", flexDirection: "column",
    width: 420, minWidth: 320, maxWidth: "50vw",
    height: "100%",
    borderLeft: "1px solid rgba(255,255,255,0.08)",
    background: "#000",
    position: "relative",
    flexShrink: 0,
  },
  toolbar: {
    position: "absolute", top: 8, right: 8, zIndex: 2,
    display: "flex", alignItems: "center",
    gap: 4,
  },
  toolBtn: {
    width: 30, height: 30,
    borderRadius: "50%",
    border: "none",
    background: "rgba(0,0,0,0.4)",
    color: "rgba(255,255,255,0.7)",
    fontSize: 14,
    cursor: "pointer",
    display: "flex", alignItems: "center", justifyContent: "center",
    backdropFilter: "blur(6px)",
    transition: "background 0.15s, color 0.15s",
  },
  iframe: {
    flex: 1, width: "100%", border: "none",
    background: "#000",
  },
  debugPanel: {
    position: "absolute",
    top: 48, left: 8, bottom: 8,
    width: 340,
    zIndex: 3,
    background: "rgba(11,16,32,0.95)",
    borderRadius: 12,
    display: "flex", flexDirection: "column",
    overflow: "hidden",
    boxShadow: "0 8px 32px rgba(0,0,0,0.3)",
  },
};

const fullscreenStyles: Record<string, React.CSSProperties> = {
  container: {
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
};
