import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { FileNode, FileTreeResponse } from "../types";
import { FileTree } from "./FileTree";
import { FileEditor } from "./FileEditor";
import { ImagePreview } from "./ImagePreview";

interface Props {
  appId: string;
  onRun: () => void;
}

export function SkillEditor({ appId, onRun }: Props) {
  const [tree, setTree] = useState<FileTreeResponse | null>(null);
  const [selected, setSelected] = useState<FileNode | null>(null);
  const [err, setErr] = useState("");

  const reload = useCallback(async () => {
    try {
      setTree(await api.fileTree(appId));
    } catch (e: any) {
      setErr(String(e.message || e));
    }
  }, [appId]);

  useEffect(() => {
    setSelected(null);
    reload();
  }, [appId, reload]);

  const newFile = async () => {
    const path = window.prompt("新文件相对路径(例如 scripts/foo.py)");
    if (!path) return;
    await api.writeFile(appId, path, "");
    await reload();
  };

  const del = async () => {
    if (!selected) return;
    if (!window.confirm(`删除 ${selected.path}?`)) return;
    await api.deleteFile(appId, selected.path);
    setSelected(null);
    await reload();
  };

  return (
    <div className="frame-wrap">
      <div className="frame-toolbar">
        <span className="t-title">编辑技能文件</span>
        <span className="t-sub">· {appId} · 拖拽上传 / 移动 · 编辑文本 · 预览图片</span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button className="btn" onClick={newFile}>
            新建文件
          </button>
          <button className="btn" onClick={del} disabled={!selected}>
            删除
          </button>
          <button className="btn btn-primary" onClick={onRun}>
            运行
          </button>
        </div>
      </div>
      {err && <div style={{ color: "#ef4444", padding: 8 }}>{err}</div>}
      <div className="editor-layout">
        {tree && (
          <FileTree
            appId={appId}
            nodes={tree.children}
            selectedPath={selected?.path ?? null}
            onSelect={setSelected}
            onChanged={reload}
          />
        )}
        {!selected && <div className="empty">选择左侧文件进行编辑,或把文件拖到文件夹上传。</div>}
        {selected && selected.kind === "text" && (
          <FileEditor key={selected.path} appId={appId} path={selected.path} />
        )}
        {selected && selected.kind === "image" && (
          <ImagePreview key={selected.path} appId={appId} path={selected.path} />
        )}
        {selected && selected.kind === "binary" && (
          <div className="empty">二进制文件,不支持预览/编辑。</div>
        )}
      </div>
    </div>
  );
}
