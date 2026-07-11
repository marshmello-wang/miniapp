import type { AppInfo } from "../types";

interface Props {
  apps: AppInfo[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onEdit: (id: string) => void;
}

const GRADIENTS = [
  "linear-gradient(135deg,#6366f1,#8b5cf6)",
  "linear-gradient(135deg,#0ea5e9,#22d3ee)",
  "linear-gradient(135deg,#f43f5e,#fb7185)",
  "linear-gradient(135deg,#10b981,#34d399)",
  "linear-gradient(135deg,#f59e0b,#fbbf24)",
  "linear-gradient(135deg,#8b5cf6,#ec4899)",
];

function avatarFor(id: string): { bg: string; ch: string } {
  let hash = 0;
  for (let i = 0; i < id.length; i++) hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
  return { bg: GRADIENTS[hash % GRADIENTS.length], ch: (id[0] || "?").toUpperCase() };
}

export function AppList({ apps, selectedId, onSelect, onEdit }: Props) {
  if (apps.length === 0) {
    return (
      <div className="empty" style={{ height: "auto", padding: "36px 20px", color: "var(--side-muted)" }}>
        <div style={{ fontSize: 13 }}>还没有小程序</div>
        <div style={{ fontSize: 12, opacity: 0.8 }}>点下方「新建小程序」创建一个</div>
      </div>
    );
  }
  return (
    <div className="app-list">
      {apps.map((app) => {
        const av = avatarFor(app.id);
        return (
          <div
            key={app.id}
            className={`app-item ${selectedId === app.id ? "active" : ""}`}
            onClick={() => onSelect(app.id)}
          >
            <div className="app-avatar" style={{ background: av.bg }}>
              {(app.name || app.id)[0]?.toUpperCase() || av.ch}
            </div>
            <div className="meta">
              <div className="name">{app.name}</div>
              <div className="desc">{app.description || app.id}</div>
            </div>
            <button
              className="edit"
              title="编辑技能文件"
              onClick={(e) => {
                e.stopPropagation();
                onEdit(app.id);
              }}
            >
              ✎
            </button>
          </div>
        );
      })}
    </div>
  );
}
