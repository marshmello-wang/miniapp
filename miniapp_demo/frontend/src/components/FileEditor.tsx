import { useEffect, useState } from "react";
import { api } from "../api/client";

export function FileEditor({ appId, path }: { appId: string; path: string }) {
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    setLoading(true);
    setErr("");
    api
      .readFile(appId, path)
      .then((r) => {
        setContent(r.content);
        setDirty(false);
      })
      .catch((e) => setErr(String(e.message || e)))
      .finally(() => setLoading(false));
  }, [appId, path]);

  const save = async () => {
    try {
      await api.writeFile(appId, path, content);
      setDirty(false);
      setSaved(true);
      setTimeout(() => setSaved(false), 1200);
    } catch (e: any) {
      setErr(String(e.message || e));
    }
  };

  return (
    <div className="editor-main">
      <div className="editor-toolbar">
        <strong>{path}</strong>
        {dirty && <span className="muted">· 未保存</span>}
        {saved && <span className="muted">· 已保存</span>}
        <button className="btn btn-primary" style={{ marginLeft: "auto" }} onClick={save} disabled={loading}>
          保存 (⌘S)
        </button>
      </div>
      {err && <div style={{ color: "#ef4444", padding: 8 }}>{err}</div>}
      <textarea
        className="code-area"
        value={loading ? "加载中…" : content}
        spellCheck={false}
        onChange={(e) => {
          setContent(e.target.value);
          setDirty(true);
        }}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === "s") {
            e.preventDefault();
            save();
          }
        }}
      />
    </div>
  );
}
