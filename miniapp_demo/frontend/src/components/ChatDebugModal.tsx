import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { ChatMsg, DebugEvent } from "./ChatMessages";

interface Props {
  msg: ChatMsg;
  sessionId: string;
  onClose: () => void;
}

interface HistoryEntry {
  role: string;
  content: string;
  source?: string;
}

interface DebugData {
  system_prompt: string;
  input_history: HistoryEntry[];
  user_input: string;
  trajectory: any[];
}

type Tab = "trajectory" | "system_prompt" | "history";

export function ChatDebugModal({ msg, sessionId, onClose }: Props) {
  const [tab, setTab] = useState<Tab>("trajectory");
  const [debugData, setDebugData] = useState<DebugData | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (msg.roundIdx === undefined) return;
    setLoading(true);
    api
      .getChatRoundDebug(sessionId, msg.roundIdx)
      .then(setDebugData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [sessionId, msg.roundIdx]);

  const handleOverlayClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose],
  );

  const tabs: { key: Tab; label: string }[] = [
    { key: "trajectory", label: "行为轨迹" },
    { key: "system_prompt", label: "System Prompt" },
    { key: "history", label: "Input History" },
  ];

  return (
    <div style={styles.overlay} onClick={handleOverlayClick}>
      <div style={styles.modal}>
        <div style={styles.header}>
          <span style={styles.title}>Debug — Round #{msg.roundIdx}</span>
          <button style={styles.closeBtn} onClick={onClose}>✕</button>
        </div>

        <div style={styles.tabBar}>
          {tabs.map((t) => (
            <button
              key={t.key}
              style={{
                ...styles.tab,
                ...(tab === t.key ? styles.tabActive : {}),
              }}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div style={styles.body}>
          {loading && <div style={styles.loading}>加载中…</div>}

          {tab === "trajectory" && (
            <TrajectoryView events={msg.events} stored={debugData?.trajectory} />
          )}
          {tab === "system_prompt" && (
            <pre style={styles.pre}>
              {debugData?.system_prompt || "(加载中…)"}
            </pre>
          )}
          {tab === "history" && (
            <HistoryView
              history={debugData?.input_history}
              userInput={debugData?.user_input}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function TrajectoryView({
  events,
  stored,
}: {
  events?: DebugEvent[];
  stored?: any[];
}) {
  const items = events && events.length > 0 ? events : stored;
  if (!items || items.length === 0) {
    return <div style={styles.empty}>无轨迹数据</div>;
  }

  return (
    <div style={styles.trajList}>
      {items.map((item, i) => {
        const evType = item.type || item.event_type || "unknown";
        return (
          <div key={i} style={styles.trajItem}>
            <div style={styles.trajBadge}>
              <span style={badgeColor(evType)}>{evType}</span>
              {item.ts && (
                <span style={styles.trajTs}>
                  {new Date(item.ts * 1000).toLocaleTimeString("zh-CN", {
                    hour: "2-digit", minute: "2-digit", second: "2-digit",
                  })}
                </span>
              )}
            </div>
            <pre style={styles.trajPre}>
              {formatPayload(item)}
            </pre>
          </div>
        );
      })}
    </div>
  );
}

function HistoryView({
  history,
  userInput,
}: {
  history?: HistoryEntry[];
  userInput?: string;
}) {
  if (!history) return <div style={styles.empty}>加载中…</div>;

  const roleColor = (role: string) =>
    role === "user" ? "#1976d2" : "#7b1fa2";

  const sourceLabel = (h: HistoryEntry) => {
    if (!h.source || h.source === "chat") return "";
    if (h.source.startsWith("miniapp:"))
      return ` [${h.source.split(":")[1]}]`;
    return ` [${h.source}]`;
  };

  return (
    <div style={styles.histList}>
      {history.map((h, i) => (
        <div key={i} style={styles.histItem}>
          <span
            style={{
              ...styles.histRole,
              color: roleColor(h.role),
            }}
          >
            {h.role}{sourceLabel(h)}
          </span>
          <pre style={styles.histContent}>{h.content}</pre>
        </div>
      ))}
      {userInput && (
        <div style={styles.histItem}>
          <span style={{ ...styles.histRole, color: "#1976d2" }}>
            user (当前)
          </span>
          <pre style={styles.histContent}>{userInput}</pre>
        </div>
      )}
      {history.length === 0 && !userInput && (
        <div style={styles.empty}>无历史消息（首轮对话）</div>
      )}
    </div>
  );
}

function formatPayload(item: any): string {
  const payload = item.payload || item.content;
  if (!payload) return JSON.stringify(item, null, 2);
  return typeof payload === "string"
    ? payload
    : JSON.stringify(payload, null, 2);
}

function badgeColor(type: string): React.CSSProperties {
  const colors: Record<string, string> = {
    thinking: "#ff9800",
    text: "#4caf50",
    tool_call: "#2196f3",
    tool_result: "#9c27b0",
    ui_update: "#00bcd4",
    done: "#607d8b",
    reasoning: "#ff9800",
  };
  return {
    padding: "1px 8px",
    borderRadius: 4,
    fontSize: 11,
    fontWeight: 700,
    color: "#fff",
    background: colors[type] || "#888",
  };
}

const styles: Record<string, React.CSSProperties> = {
  overlay: {
    position: "fixed", inset: 0, zIndex: 10000,
    background: "rgba(0,0,0,0.4)",
    display: "flex", alignItems: "center", justifyContent: "center",
    fontFamily: '"PingFang SC", system-ui, sans-serif',
  },
  modal: {
    width: "min(860px, 90vw)",
    maxHeight: "85vh",
    background: "#fff",
    borderRadius: 16,
    display: "flex", flexDirection: "column",
    boxShadow: "0 24px 80px rgba(0,0,0,0.2)",
    overflow: "hidden",
  },
  header: {
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "16px 20px",
    borderBottom: "1px solid #f0f0f0",
  },
  title: {
    fontSize: 16, fontWeight: 700, color: "#333",
  },
  closeBtn: {
    background: "none", border: "none",
    fontSize: 18, color: "#aaa", cursor: "pointer",
    padding: "4px 8px",
  },
  tabBar: {
    display: "flex", gap: 0,
    borderBottom: "1px solid #f0f0f0",
    padding: "0 20px",
  },
  tab: {
    padding: "10px 18px",
    background: "none", border: "none", borderBottom: "2px solid transparent",
    fontSize: 13, fontWeight: 500, color: "#888",
    cursor: "pointer",
    transition: "color 0.15s, border-color 0.15s",
  },
  tabActive: {
    color: "#333",
    borderBottom: "2px solid #667eea",
    fontWeight: 600,
  },
  body: {
    flex: 1, overflow: "auto",
    padding: "16px 20px",
  },
  loading: {
    textAlign: "center" as const, color: "#aaa",
    padding: "40px 0", fontSize: 14,
  },
  empty: {
    textAlign: "center" as const, color: "#ccc",
    padding: "40px 0", fontSize: 14,
  },
  pre: {
    margin: 0,
    whiteSpace: "pre-wrap" as const, wordBreak: "break-word" as const,
    fontSize: 13, lineHeight: 1.6,
    fontFamily: 'ui-monospace, Menlo, "Cascadia Code", monospace',
    color: "#333",
    background: "#f8f9fb",
    padding: 16, borderRadius: 10,
  },
  trajList: {
    display: "flex", flexDirection: "column" as const, gap: 8,
  },
  trajItem: {
    borderRadius: 10,
    border: "1px solid #f0f0f0",
    overflow: "hidden",
  },
  trajBadge: {
    display: "flex", alignItems: "center", gap: 8,
    padding: "6px 10px",
    background: "#fafafa",
  },
  trajTs: {
    fontSize: 11, color: "#bbb",
    fontFamily: 'ui-monospace, monospace',
  },
  trajPre: {
    margin: 0,
    padding: "8px 12px",
    fontSize: 12, lineHeight: 1.5,
    whiteSpace: "pre-wrap" as const, wordBreak: "break-word" as const,
    fontFamily: 'ui-monospace, Menlo, monospace',
    color: "#555",
    maxHeight: 200, overflow: "auto",
  },
  histList: {
    display: "flex", flexDirection: "column" as const, gap: 10,
  },
  histItem: {
    borderRadius: 10,
    border: "1px solid #f0f0f0",
    overflow: "hidden",
  },
  histRole: {
    display: "block",
    padding: "6px 12px",
    background: "#fafafa",
    fontSize: 12, fontWeight: 700,
    textTransform: "uppercase" as const,
  },
  histContent: {
    margin: 0,
    padding: "8px 12px",
    fontSize: 13, lineHeight: 1.5,
    whiteSpace: "pre-wrap" as const, wordBreak: "break-word" as const,
    fontFamily: 'ui-monospace, Menlo, monospace',
    color: "#444",
    maxHeight: 200, overflow: "auto",
  },
};
