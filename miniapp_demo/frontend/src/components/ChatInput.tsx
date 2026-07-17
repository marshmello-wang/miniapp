import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";

interface AppShortcut {
  id: string;
  name: string;
}

interface Props {
  onSend: (text: string) => void;
  disabled?: boolean;
  isMobile?: boolean;
  onOpenApp?: (appId: string) => void;
}

export function ChatInput({ onSend, disabled, isMobile, onOpenApp }: Props) {
  const [apps, setApps] = useState<AppShortcut[]>([]);

  useEffect(() => {
    api.listApps().then((list) => setApps(list.map((a) => ({ id: a.id, name: a.name }))));
  }, []);
  const [text, setText] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const submit = useCallback(() => {
    const v = text.trim();
    if (!v || disabled) return;
    onSend(v);
    setText("");
    inputRef.current?.focus();
  }, [text, disabled, onSend]);

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        submit();
      }
    },
    [submit],
  );

  return (
    <div style={{ ...styles.bar, ...(isMobile ? styles.barMobile : {}) }}>
      {apps.length > 0 && onOpenApp && (
        <div style={styles.shortcuts}>
          {apps.map((app) => (
            <button
              key={app.id}
              style={styles.shortcutBtn}
              onClick={() => onOpenApp(app.id)}
              title={app.name}
            >
              <span style={styles.shortcutIcon}>⬡</span>
              <span style={styles.shortcutName}>{app.name}</span>
            </button>
          ))}
        </div>
      )}
      <div style={styles.inputWrap}>
        <textarea
          ref={inputRef}
          style={styles.input}
          placeholder="输入消息…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          disabled={disabled}
        />
        <button
          style={{
            ...styles.sendBtn,
            opacity: text.trim() && !disabled ? 1 : 0.4,
          }}
          disabled={!text.trim() || disabled}
          onClick={submit}
        >
          ↑
        </button>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  bar: {
    padding: "12px 24px 20px",
    borderTop: "1px solid #f0f0f0",
    background: "#fff",
  },
  barMobile: {
    padding: "8px 12px 12px",
  },
  shortcuts: {
    display: "flex", gap: 8,
    marginBottom: 8,
    overflowX: "auto",
  },
  shortcutBtn: {
    display: "flex", alignItems: "center", gap: 4,
    padding: "5px 12px",
    borderRadius: 20,
    border: "1px solid #e8e8f0",
    background: "#fafafe",
    cursor: "pointer",
    fontSize: 13,
    color: "#555",
    whiteSpace: "nowrap" as const,
    transition: "background 0.15s, border-color 0.15s",
    flexShrink: 0,
  },
  shortcutIcon: {
    fontSize: 14, color: "#667eea",
  },
  shortcutName: {
    color: "#444",
  },
  inputWrap: {
    display: "flex", alignItems: "flex-end", gap: 8,
    background: "#f5f5f5",
    borderRadius: 16,
    padding: "8px 8px 8px 16px",
  },
  input: {
    flex: 1,
    border: "none", outline: "none",
    background: "transparent",
    fontSize: 15, lineHeight: 1.5,
    resize: "none" as const,
    fontFamily: '"PingFang SC", system-ui, sans-serif',
    maxHeight: 120,
    color: "#1a1a2e",
  },
  sendBtn: {
    width: 36, height: 36, flexShrink: 0,
    borderRadius: "50%",
    border: "none",
    background: "linear-gradient(135deg, #667eea, #764ba2)",
    color: "#fff",
    fontSize: 18, fontWeight: 700,
    cursor: "pointer",
    display: "flex", alignItems: "center", justifyContent: "center",
    transition: "opacity 0.15s",
  },
};
