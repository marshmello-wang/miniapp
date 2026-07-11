import { useState } from "react";
import type { DebugFrame } from "../types";

function frameType(f: DebugFrame): string {
  const fr = f.frame || {};
  if (fr.data_type === "app.event") return `app.event · ${fr.data?.type ?? "?"}`;
  return fr.data_type || fr.type || "?";
}

function DebugRow({ f }: { f: DebugFrame }) {
  const [open, setOpen] = useState(false);
  const time = new Date(f.ts * 1000).toLocaleTimeString();
  return (
    <div className="debug-item">
      <div className="debug-row" onClick={() => setOpen((o) => !o)}>
        <span className={`badge ${f.dir}`}>{f.dir === "up" ? "↑ UP" : "↓ DOWN"}</span>
        <span className="badge type">{frameType(f)}</span>
        <span className="debug-time">{time}</span>
      </div>
      {open && <pre className="debug-json">{JSON.stringify(f.frame, null, 2)}</pre>}
    </div>
  );
}

export function DebugPanel({ frames }: { frames: DebugFrame[] }) {
  if (frames.length === 0) {
    return (
      <div className="empty">
        <div className="empty-glyph" style={{ fontSize: 24 }}>⇅</div>
        <div className="empty-title">暂无通信</div>
        <div className="empty-hint">打开一个小程序并交互,上/下行帧会在这里逐条出现。</div>
      </div>
    );
  }
  return (
    <div className="debug-list">
      {[...frames].reverse().map((f, i) => (
        <DebugRow key={frames.length - i} f={f} />
      ))}
    </div>
  );
}
