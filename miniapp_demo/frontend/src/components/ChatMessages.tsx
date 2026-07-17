import { useEffect, useRef, useState } from "react";

export interface DebugEvent {
  type: string;
  payload: any;
  ts?: number;
}

export interface ChatMsg {
  id: string;
  role: "user" | "assistant" | "miniapp";
  content: string;
  /** 后端 round 索引,用于拉取完整 debug 信息 */
  roundIdx?: number;
  /** 流式收集的事件轨迹 */
  events?: DebugEvent[];
  /** miniapp 摘要卡片专用 */
  appId?: string;
  roundCount?: number;
  miniappMessages?: { role: string; content: string }[];
}

interface Props {
  messages: ChatMsg[];
  streaming: boolean;
  isMobile?: boolean;
  onSkillClick?: (skillName: string) => void;
  onDebug?: (msg: ChatMsg) => void;
}

function MiniappCard({ msg, isMobile, onSkillClick }: { msg: ChatMsg; isMobile?: boolean; onSkillClick?: (s: string) => void }) {
  const [expanded, setExpanded] = useState(false);
  const appId = msg.appId || "unknown";
  const rounds = msg.roundCount || 0;
  return (
    <div style={styles.miniappRow}>
      <div style={{ ...styles.miniappCard, ...(isMobile ? { maxWidth: "100%" } : {}) }}>
        <div style={styles.miniappHeader} onClick={() => setExpanded(!expanded)}>
          <span style={styles.miniappIcon}>📱</span>
          <span style={styles.miniappTitle}>{appId} 对话</span>
          <span style={styles.miniappBadge}>{rounds} 轮</span>
          <span style={styles.miniappArrow}>{expanded ? "▾" : "▸"}</span>
        </div>
        {expanded && (
          <div style={styles.miniappSummary}>
            {msg.miniappMessages && msg.miniappMessages.length > 0 ? (
              msg.miniappMessages.map((m, i) => (
                <div key={i} style={styles.miniappMsg}>
                  <span style={{
                    ...styles.miniappMsgRole,
                    color: m.role === "user" ? "#1976d2" : "#7c5cff",
                  }}>
                    {m.role === "user" ? "你" : "AI"}
                  </span>
                  <span style={styles.miniappMsgText}>{m.content}</span>
                </div>
              ))
            ) : (
              msg.content && <div>{msg.content}</div>
            )}
          </div>
        )}
        <div
          style={styles.miniappOpen}
          onClick={() => onSkillClick?.(appId)}
        >
          继续对话
        </div>
      </div>
    </div>
  );
}

export function ChatMessages({ messages, streaming, isMobile, onSkillClick, onDebug }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  const containerStyle = isMobile
    ? { ...styles.container, padding: "12px 12px" }
    : styles.container;

  const bubbleMaxWidth = isMobile ? "88%" : "72%";

  return (
    <div style={containerStyle}>
      {messages.length === 0 && !streaming && (
        <div style={styles.empty}>
          <div style={styles.emptyIcon}>💬</div>
          <div style={styles.emptyText}>开始一段对话吧</div>
        </div>
      )}
      {messages.filter(Boolean).map((msg) =>
        msg.role === "miniapp" ? (
          <MiniappCard key={msg.id} msg={msg} isMobile={isMobile} onSkillClick={onSkillClick} />
        ) : (
        <div key={msg.id} style={styles.row}>
          <div
            style={{
              ...styles.bubble,
              maxWidth: bubbleMaxWidth,
              ...(msg.role === "user" ? styles.userBubble : styles.aiBubble),
              alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
            }}
          >
            <div style={styles.roleLine}>
              <span style={styles.roleLabel}>
                {msg.role === "user" ? "你" : "AI"}
              </span>
              {msg.role === "assistant" && msg.roundIdx !== undefined && (
                <button
                  style={styles.debugBtn}
                  onClick={() => onDebug?.(msg)}
                  title="查看调试信息"
                >
                  Debug
                </button>
              )}
            </div>
            <div style={styles.text}>{msg.content}</div>
          </div>
        </div>
        ),
      )}
      {streaming && (
        <div style={styles.row}>
          <div style={{ ...styles.bubble, ...styles.aiBubble, alignSelf: "flex-start" }}>
            <div style={styles.roleLabel}>AI</div>
            <div style={styles.typing}>
              <span style={styles.dot} />
              <span style={{ ...styles.dot, animationDelay: "0.2s" }} />
              <span style={{ ...styles.dot, animationDelay: "0.4s" }} />
            </div>
          </div>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    flex: 1, overflow: "auto",
    padding: "20px 24px",
    display: "flex", flexDirection: "column", gap: 4,
  },
  empty: {
    flex: 1, display: "flex", flexDirection: "column",
    alignItems: "center", justifyContent: "center",
    color: "#ccc",
  },
  emptyIcon: { fontSize: 48, marginBottom: 12 },
  emptyText: { fontSize: 15, color: "#bbb" },
  row: {
    display: "flex", flexDirection: "column",
  },
  bubble: {
    maxWidth: "72%",
    padding: "12px 16px",
    borderRadius: 16,
    fontSize: 15,
    lineHeight: 1.7,
    wordBreak: "break-word" as const,
  },
  userBubble: {
    background: "#e3f2fd",
    borderBottomRightRadius: 4,
  },
  aiBubble: {
    background: "#f5f5f5",
    borderBottomLeftRadius: 4,
  },
  roleLine: {
    display: "flex", alignItems: "center", gap: 6,
    marginBottom: 4,
  },
  roleLabel: {
    fontSize: 11, fontWeight: 600, color: "#999",
    letterSpacing: "0.05em",
  },
  debugBtn: {
    fontSize: 10, fontWeight: 600,
    padding: "1px 6px",
    borderRadius: 4,
    border: "1px solid #ddd",
    background: "#fff",
    color: "#aaa",
    cursor: "pointer",
    lineHeight: "16px",
    transition: "color 0.15s, border-color 0.15s",
  },
  text: {
    whiteSpace: "pre-wrap" as const,
    color: "#1a1a2e",
  },
  typing: {
    display: "flex", gap: 4, padding: "4px 0",
  },
  dot: {
    width: 7, height: 7, borderRadius: "50%",
    background: "#bbb",
    animation: "dotPulse 1s infinite",
  },
  miniappRow: {
    display: "flex", flexDirection: "column" as const, alignItems: "flex-start",
    padding: "8px 0",
  },
  miniappCard: {
    maxWidth: 320,
    background: "#f5f5f5",
    borderRadius: 16,
    borderBottomLeftRadius: 4,
    border: "1px solid #e8e8f0",
    overflow: "hidden",
  },
  miniappHeader: {
    display: "flex", alignItems: "center", gap: 8,
    padding: "12px 16px",
    cursor: "pointer",
    userSelect: "none" as const,
  },
  miniappIcon: { fontSize: 20 },
  miniappTitle: {
    flex: 1, fontSize: 14, fontWeight: 600, color: "#333",
  },
  miniappBadge: {
    fontSize: 11, color: "#7c5cff", fontWeight: 600,
    background: "rgba(124,92,255,0.1)",
    padding: "2px 8px", borderRadius: 99,
  },
  miniappArrow: { fontSize: 12, color: "#999" },
  miniappSummary: {
    padding: "10px 16px",
    fontSize: 13, lineHeight: 1.6, color: "#666",
    borderTop: "1px solid rgba(0,0,0,0.05)",
    maxHeight: 300, overflowY: "auto" as const,
    display: "flex", flexDirection: "column" as const, gap: 8,
  },
  miniappMsg: {
    display: "flex", gap: 6, alignItems: "flex-start",
  },
  miniappMsgRole: {
    flexShrink: 0, fontSize: 11, fontWeight: 700,
    minWidth: 20,
  },
  miniappMsgText: {
    fontSize: 13, lineHeight: 1.6, color: "#444",
    whiteSpace: "pre-wrap" as const, wordBreak: "break-word" as const,
  },
  miniappOpen: {
    padding: "8px 16px",
    fontSize: 13, color: "#7c5cff",
    cursor: "pointer",
    borderTop: "1px solid rgba(0,0,0,0.05)",
    textAlign: "center" as const,
    fontWeight: 500,
    transition: "background 0.15s",
  },
};
