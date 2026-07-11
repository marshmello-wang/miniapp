import { useState } from "react";
import { api } from "../api/client";

interface Props {
  onClose: () => void;
  onCreated: (appId: string) => void;
}

export function NewAppDialog({ onClose, onCreated }: Props) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const submit = async () => {
    if (!name.trim()) {
      setErr("请填写名称");
      return;
    }
    setBusy(true);
    setErr("");
    try {
      const manifest = await api.createApp(name.trim(), description.trim());
      onCreated(manifest.id);
    } catch (e: any) {
      setErr(String(e.message || e));
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>新建小程序</h3>
        <div className="modal-sub">会生成一个最小可用的 Skill 包脚手架,创建后进入文件编辑。</div>
        <div className="field">
          <label>名称</label>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="例如 订单审核" />
        </div>
        <div className="field">
          <label>描述</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            placeholder="这个小程序做什么"
          />
        </div>
        {err && <div style={{ color: "#ef4444", fontSize: 13 }}>{err}</div>}
        <div className="row-end">
          <button className="btn" onClick={onClose} disabled={busy}>
            取消
          </button>
          <button className="btn btn-primary" onClick={submit} disabled={busy}>
            {busy ? "创建中…" : "创建"}
          </button>
        </div>
      </div>
    </div>
  );
}
