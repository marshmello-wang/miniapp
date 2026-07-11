import { useEffect, useState } from "react";
import { api } from "../api/client";

export function SettingsPanel() {
  const [cfg, setCfg] = useState<any>(null);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.getConfig().then(setCfg).catch((e) => setErr(String(e)));
  }, []);

  if (!cfg) return <div className="settings">加载配置…{err}</div>;

  const llm = cfg.llm || {};
  const agent = cfg.agent || {};

  const setLlm = (k: string, v: any) => setCfg({ ...cfg, llm: { ...llm, [k]: v } });
  const setAgent = (k: string, v: any) => setCfg({ ...cfg, agent: { ...agent, [k]: v } });

  const save = async () => {
    setErr("");
    try {
      const next = await api.updateConfig({ llm: cfg.llm, agent: cfg.agent });
      setCfg(next);
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    } catch (e: any) {
      setErr(String(e.message || e));
    }
  };

  return (
    <div className="settings">
      <h2>LLM 配置</h2>
      <p className="settings-lead">agentAction 使用真实 LLM,请填写可用的 API Key。配置存于 <code>~/.miniapp/config.json</code>。direct_action 不需要 LLM。</p>
      <div className="field">
        <label>Provider</label>
        <select value={llm.provider || "claude"} onChange={(e) => setLlm("provider", e.target.value)}>
          <option value="claude">claude</option>
          <option value="openai">openai</option>
          <option value="gemini">gemini</option>
          <option value="kimi">kimi</option>
        </select>
      </div>
      <div className="field">
        <label>Model</label>
        <input value={llm.model || ""} onChange={(e) => setLlm("model", e.target.value)} />
      </div>
      <div className="field">
        <label>API Key</label>
        <input
          type="password"
          value={llm.api_key || ""}
          onChange={(e) => setLlm("api_key", e.target.value)}
          placeholder="sk-…"
        />
      </div>
      <div className="field">
        <label>Base URL(可选,私有/代理端点)</label>
        <input value={llm.base_url || ""} onChange={(e) => setLlm("base_url", e.target.value || null)} />
      </div>

      <h2>Agent</h2>
      <div className="field">
        <label>max_iterations</label>
        <input
          type="number"
          value={agent.max_iterations ?? 20}
          onChange={(e) => setAgent("max_iterations", Number(e.target.value))}
        />
      </div>
      <div className="field">
        <label>temperature</label>
        <input
          type="number"
          step="0.1"
          value={agent.temperature ?? 0.7}
          onChange={(e) => setAgent("temperature", Number(e.target.value))}
        />
      </div>

      {err && <div className="err">{err}</div>}
      <div className="row-end">
        {saved && <span className="muted" style={{ alignSelf: "center" }}>已保存</span>}
        <button className="btn btn-primary" onClick={save}>
          保存
        </button>
      </div>
    </div>
  );
}
