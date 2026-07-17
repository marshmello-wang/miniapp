import {
  forwardRef,
  useImperativeHandle,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { ConversationBridge } from "../host/conversationBridge";
import { DebugPanel } from "./DebugPanel";
import type { DurableEvent } from "../conversations/types";
import type { DebugFrame } from "../types";

interface Props {
  appId: string;
  appName?: string;
  conversationId: string;
  onClose: () => void;
}

export interface SkillPanelHandle {
  uiInstanceId: string;
  handleConversationEvent: (event: DurableEvent) => void;
}

export const SkillPanel = forwardRef<SkillPanelHandle, Props>(function SkillPanel(
  { appId, appName, conversationId, onClose },
  ref,
) {
  const [showDebug, setShowDebug] = useState(false);
  const [frames, setFrames] = useState<DebugFrame[]>([]);
  const [loading, setLoading] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const bridgeRef = useRef<ConversationBridge | null>(null);
  const revisionRef = useRef(0);

  const uiInstanceId = useMemo(
    () => `ui_${appId}_${conversationId}`,
    [appId, conversationId],
  );

  useLayoutEffect(() => {
    const bridge = new ConversationBridge({
      conversationId,
      skillId: appId,
      uiInstanceId,
      onDebug: (f) => setFrames((prev) => [...prev, f]),
      onLoadingChange: setLoading,
      getRevision: () => revisionRef.current,
      setRevision: (value) => {
        revisionRef.current = value;
      },
    });
    bridgeRef.current = bridge;
    bridge.setIframe(iframeRef.current);
    return () => {
      bridge.dispose();
      bridgeRef.current = null;
    };
  }, [appId, conversationId, uiInstanceId]);

  useLayoutEffect(() => {
    bridgeRef.current?.setIframe(iframeRef.current);
  });

  useImperativeHandle(ref, () => ({
    uiInstanceId,
    handleConversationEvent(event: DurableEvent) {
      void bridgeRef.current?.handleConversationEvent(event);
    },
  }), [uiInstanceId]);

  const uiUrl =
    `/api/apps/${appId}/ui/index.html` +
    `?conversationId=${encodeURIComponent(conversationId)}` +
    `&uiInstanceId=${encodeURIComponent(uiInstanceId)}`;
  const title = appName || appId;

  return (
    <div style={styles.panel}>
      <div style={styles.toolbar}>
        <div style={styles.toolbarLeft}>
          <span style={styles.dot} />
          <span style={styles.title}>{title}</span>
          {loading && <span style={styles.loadingBadge}>Agent 处理中…</span>}
        </div>
        <div style={styles.toolbarRight}>
          <button
            className="skill-tool-btn"
            style={{
              ...styles.toolBtn,
              ...(showDebug ? styles.toolBtnActive : {}),
            }}
            onClick={() => setShowDebug((v) => !v)}
            title="Debug"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 20V10" /><path d="M18 20V4" /><path d="M6 20v-4" />
            </svg>
          </button>
          <button className="skill-tool-btn" style={styles.toolBtn} onClick={onClose} title="关闭">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      </div>

      <div style={styles.body}>
        <iframe
          ref={iframeRef}
          src={uiUrl}
          style={styles.iframe}
          allow="microphone"
        />
      </div>

      {showDebug && (
        <div style={styles.debugOverlay}>
          <div style={styles.debugHeader}>
            <span style={styles.debugTitle}>通信调试</span>
            <button style={styles.debugClearBtn} onClick={() => setFrames([])}>清空</button>
            <button style={styles.debugCloseBtn} onClick={() => setShowDebug(false)}>✕</button>
          </div>
          <div style={styles.debugBody}>
            <DebugPanel frames={frames} />
          </div>
        </div>
      )}
    </div>
  );
});

const styles: Record<string, React.CSSProperties> = {
  panel: {
    display: "flex",
    flexDirection: "column",
    height: "100%",
    background: "#fff",
    borderLeft: "1px solid #e8e8f0",
    position: "relative",
    overflow: "hidden",
  },
  toolbar: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "10px 14px",
    borderBottom: "1px solid #f0f0f0",
    background: "#fafafa",
    flexShrink: 0,
  },
  toolbarLeft: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    minWidth: 0,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: "50%",
    background: "linear-gradient(135deg, #667eea, #764ba2)",
    flexShrink: 0,
  },
  title: {
    fontSize: 13,
    fontWeight: 600,
    color: "#333",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap" as const,
  },
  loadingBadge: {
    fontSize: 11,
    color: "#667eea",
    background: "rgba(102,126,234,0.1)",
    padding: "2px 8px",
    borderRadius: 999,
    flexShrink: 0,
  },
  toolbarRight: {
    display: "flex",
    alignItems: "center",
    gap: 4,
    flexShrink: 0,
  },
  toolBtn: {
    width: 30,
    height: 30,
    borderRadius: 8,
    border: "none",
    background: "transparent",
    color: "#999",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    transition: "background 0.15s, color 0.15s",
  },
  toolBtnActive: {
    background: "rgba(102,126,234,0.12)",
    color: "#667eea",
  },
  body: {
    flex: 1,
    position: "relative" as const,
    overflow: "hidden",
  },
  iframe: {
    position: "absolute" as const,
    inset: 0,
    width: "100%",
    height: "100%",
    border: "none",
  },
  debugOverlay: {
    position: "absolute" as const,
    inset: 0,
    top: 44,
    zIndex: 3,
    background: "rgba(11,16,32,0.95)",
    display: "flex",
    flexDirection: "column" as const,
    backdropFilter: "blur(12px)",
  },
  debugHeader: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "10px 14px",
    borderBottom: "1px solid rgba(255,255,255,0.1)",
    flexShrink: 0,
  },
  debugTitle: {
    flex: 1,
    color: "#fff",
    fontSize: 13,
    fontWeight: 600,
  },
  debugClearBtn: {
    background: "rgba(255,255,255,0.1)",
    border: "none",
    borderRadius: 6,
    color: "#aaa",
    fontSize: 12,
    padding: "4px 10px",
    cursor: "pointer",
  },
  debugCloseBtn: {
    background: "none",
    border: "none",
    color: "#aaa",
    fontSize: 14,
    cursor: "pointer",
    padding: "4px 6px",
  },
  debugBody: {
    flex: 1,
    overflow: "auto",
    padding: "8px 0",
  },
};
