import { useCallback } from "react";

interface SessionItem {
  session_id: string;
  title: string;
  updated_at: number;
  round_count: number;
}

interface Props {
  sessions: SessionItem[];
  activeId: string | null;
  username: string;
  isMobile?: boolean;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
  onLogout: () => void;
  onClose?: () => void;
}

export function SessionSidebar({
  sessions, activeId, username, isMobile, onSelect, onCreate, onDelete, onLogout, onClose,
}: Props) {
  const fmtTime = useCallback((ts: number) => {
    const d = new Date(ts * 1000);
    const now = new Date();
    if (d.toDateString() === now.toDateString()) {
      return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
    }
    return d.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
  }, []);

  const handleSelect = (id: string) => {
    onSelect(id);
    if (isMobile) onClose?.();
  };

  return (
    <div style={{ ...styles.sidebar, ...(isMobile ? styles.sidebarMobile : {}) }}>
      <div style={styles.header}>
        <div style={styles.userRow}>
          <div style={styles.avatar}>{username[0].toUpperCase()}</div>
          <span style={styles.username}>{username}</span>
          {isMobile ? (
            <button style={styles.logoutBtn} onClick={onClose} title="关闭">✕</button>
          ) : (
            <button style={styles.logoutBtn} onClick={onLogout} title="退出">✕</button>
          )}
        </div>
      </div>

      <button style={styles.newBtn} onClick={() => { onCreate(); if (isMobile) onClose?.(); }}>
        + 新对话
      </button>

      <div style={styles.list}>
        {sessions.map((s) => (
          <div
            key={s.session_id}
            style={{
              ...styles.item,
              ...(s.session_id === activeId ? styles.itemActive : {}),
            }}
            onClick={() => handleSelect(s.session_id)}
          >
            <div style={styles.itemTitle}>{s.title}</div>
            <div style={styles.itemMeta}>
              {s.round_count > 0 ? `${s.round_count} 条` : "空"}
              {" · "}
              {fmtTime(s.updated_at)}
              <span
                style={styles.deleteBtn}
                onClick={(e) => { e.stopPropagation(); onDelete(s.session_id); }}
                title="删除"
              >
                ✕
              </span>
            </div>
          </div>
        ))}
        {sessions.length === 0 && (
          <div style={styles.empty}>暂无对话</div>
        )}
      </div>

      {isMobile && (
        <div style={styles.mobileLogout}>
          <button style={styles.mobileLogoutBtn} onClick={() => { onLogout(); onClose?.(); }}>
            退出登录
          </button>
        </div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  sidebar: {
    width: 260, minWidth: 260,
    background: "#fafafa",
    borderRight: "1px solid #eee",
    display: "flex", flexDirection: "column",
    fontFamily: '"PingFang SC", system-ui, sans-serif',
  },
  sidebarMobile: {
    width: "80vw", minWidth: "unset", maxWidth: 320,
    height: "100%",
    borderRight: "none",
    boxShadow: "4px 0 24px rgba(0,0,0,0.15)",
  },
  header: {
    padding: "16px 16px 0",
  },
  userRow: {
    display: "flex", alignItems: "center", gap: 10,
    padding: "8px 0",
  },
  avatar: {
    width: 32, height: 32, borderRadius: "50%",
    background: "linear-gradient(135deg, #667eea, #764ba2)",
    color: "#fff", display: "flex", alignItems: "center", justifyContent: "center",
    fontSize: 14, fontWeight: 700, flexShrink: 0,
  },
  username: {
    flex: 1, fontSize: 14, fontWeight: 600, color: "#333",
    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" as const,
  },
  logoutBtn: {
    background: "none", border: "none", color: "#bbb", cursor: "pointer",
    fontSize: 14, padding: "4px 6px", borderRadius: 6,
  },
  newBtn: {
    margin: "12px 16px",
    padding: "10px 0",
    background: "#fff",
    border: "1px solid #e0e0e0",
    borderRadius: 10,
    fontSize: 14, fontWeight: 500, color: "#555",
    cursor: "pointer",
    transition: "background 0.15s",
  },
  list: {
    flex: 1, overflow: "auto",
    padding: "0 8px 8px",
  },
  item: {
    padding: "12px 12px",
    borderRadius: 10,
    cursor: "pointer",
    transition: "background 0.15s",
    marginBottom: 2,
  },
  itemActive: {
    background: "#e8e8f0",
  },
  itemTitle: {
    fontSize: 14, fontWeight: 500, color: "#333",
    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" as const,
  },
  itemMeta: {
    fontSize: 12, color: "#aaa", marginTop: 4,
    display: "flex", alignItems: "center", gap: 4,
  },
  deleteBtn: {
    marginLeft: "auto", cursor: "pointer", color: "#ccc",
    fontSize: 12, padding: "2px 4px", borderRadius: 4,
  },
  empty: {
    textAlign: "center" as const, color: "#ccc", fontSize: 13,
    padding: "40px 0",
  },
  mobileLogout: {
    padding: "12px 16px",
    borderTop: "1px solid #eee",
  },
  mobileLogoutBtn: {
    width: "100%", padding: "10px 0",
    background: "none", border: "1px solid #e0e0e0",
    borderRadius: 10, fontSize: 14, color: "#999",
    cursor: "pointer",
  },
};
