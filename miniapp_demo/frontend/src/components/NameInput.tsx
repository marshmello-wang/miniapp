import { useState } from "react";

interface Props {
  onSubmit: (name: string) => void;
}

export function NameInput({ onSubmit }: Props) {
  const [name, setName] = useState("");

  return (
    <div style={styles.overlay}>
      <div style={styles.card}>
        <div style={styles.icon}>💬</div>
        <h2 style={styles.title}>欢迎</h2>
        <p style={styles.subtitle}>输入你的名字开始对话</p>
        <input
          style={styles.input}
          placeholder="你的名字"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && name.trim() && onSubmit(name.trim())}
          autoFocus
        />
        <button
          style={{
            ...styles.btn,
            opacity: name.trim() ? 1 : 0.5,
            cursor: name.trim() ? "pointer" : "default",
          }}
          disabled={!name.trim()}
          onClick={() => name.trim() && onSubmit(name.trim())}
        >
          开始聊天
        </button>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  overlay: {
    position: "fixed", inset: 0,
    display: "flex", alignItems: "center", justifyContent: "center",
    background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
    fontFamily: '"PingFang SC", system-ui, sans-serif',
  },
  card: {
    background: "#fff",
    borderRadius: 20,
    padding: "48px 40px",
    width: 360,
    textAlign: "center" as const,
    boxShadow: "0 20px 60px rgba(0,0,0,0.15)",
  },
  icon: { fontSize: 48, marginBottom: 12 },
  title: {
    margin: "0 0 6px", fontSize: 22, fontWeight: 700, color: "#1a1a2e",
  },
  subtitle: {
    margin: "0 0 24px", fontSize: 14, color: "#888",
  },
  input: {
    width: "100%", padding: "12px 16px",
    border: "2px solid #e8e8f0", borderRadius: 12,
    fontSize: 16, outline: "none",
    boxSizing: "border-box" as const,
    transition: "border-color 0.2s",
    marginBottom: 16,
  },
  btn: {
    width: "100%", padding: "13px 0",
    background: "linear-gradient(135deg, #667eea, #764ba2)",
    color: "#fff", border: "none", borderRadius: 12,
    fontSize: 16, fontWeight: 600,
    transition: "opacity 0.2s",
  },
};
