import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Routes, Route } from "react-router-dom";
import { api } from "./api/client";
import { HostBridge } from "./host/bridge";
import type { AppInfo, DebugFrame } from "./types";
import { AppList } from "./components/AppList";
import { AppFrame } from "./components/AppFrame";
import { DebugPanel } from "./components/DebugPanel";
import { SkillEditor } from "./components/SkillEditor";
import { NewAppDialog } from "./components/NewAppDialog";
import { SettingsPanel } from "./components/SettingsPanel";
import { StandalonePage } from "./pages/StandalonePage";
import { ChatPage } from "./pages/ChatPage";

type View =
  | { type: "empty" }
  | { type: "run"; appId: string }
  | { type: "edit"; appId: string }
  | { type: "settings" };

function Workbench() {
  const [apps, setApps] = useState<AppInfo[]>([]);
  const [view, setView] = useState<View>({ type: "empty" });
  const [debug, setDebug] = useState<DebugFrame[]>([]);
  const [showNew, setShowNew] = useState(false);

  const bridgeRef = useRef<HostBridge | null>(null);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);

  useLayoutEffect(() => {
    const bridge = new HostBridge((f) =>
      setDebug((prev) => [...prev, f]),
    );
    bridgeRef.current = bridge;
    return () => {
      bridge.dispose();
      if (bridgeRef.current === bridge) bridgeRef.current = null;
    };
  }, []);

  const refreshApps = useCallback(async () => {
    setApps(await api.listApps());
  }, []);

  useEffect(() => {
    refreshApps();
  }, [refreshApps]);

  useLayoutEffect(() => {
    const bridge = bridgeRef.current;
    if (!bridge) return;
    if (view.type === "run") {
      bridge.setApp(view.appId);
      bridge.setIframe(iframeRef.current);
      setDebug([]);
    } else {
      bridge.setApp(null);
      bridge.setIframe(null);
    }
  }, [view]);

  const setIframe = useCallback((iframe: HTMLIFrameElement | null) => {
    iframeRef.current = iframe;
    bridgeRef.current?.setIframe(iframe);
  }, []);

  const selectedId = view.type === "run" || view.type === "edit" ? view.appId : null;

  const centerNode = useMemo(() => {
    switch (view.type) {
      case "run":
        return (
          <AppFrame
            appId={view.appId}
            onIframe={setIframe}
            onEdit={() => setView({ type: "edit", appId: view.appId })}
          />
        );
      case "edit":
        return (
          <SkillEditor appId={view.appId} onRun={() => setView({ type: "run", appId: view.appId })} />
        );
      case "settings":
        return <SettingsPanel />;
      default:
        return (
          <div className="empty">
            <div className="empty-glyph">◆</div>
            <div className="empty-title">选择一个小程序开始</div>
            <div className="empty-hint">从左侧列表打开小程序,或新建一个。右侧 Debug 面板会实时显示上下行通信。</div>
          </div>
        );
    }
  }, [setIframe, view]);

  return (
    <div className="layout">
      <div className="col col-left">
        <div className="brand">
          <div className="brand-mark">◆</div>
          <div>
            <div className="brand-title">小程序工作台</div>
            <div className="brand-sub">APP-SKILL · v0.3</div>
          </div>
        </div>
        <div className="side-label">已安装应用</div>
        <div className="col-body">
          <AppList
            apps={apps}
            selectedId={selectedId}
            onSelect={(id) => setView({ type: "run", appId: id })}
            onEdit={(id) => setView({ type: "edit", appId: id })}
          />
        </div>
        <div className="sidebar-actions">
          <button className="btn btn-primary" style={{ flex: 1 }} onClick={() => setShowNew(true)}>
            + 新建小程序
          </button>
          <button className="btn btn-ghost-dark" title="设置" onClick={() => setView({ type: "settings" })}>
            设置
          </button>
        </div>
        <div className="conn-strip">
          <span className="status-dot on" />
          POST / SSE 就绪
        </div>
      </div>

      <div className="col col-center">{centerNode}</div>

      <div className="col col-right">
        <div className="col-header">
          <div>
            <div className="h-title">通信调试</div>
            <div className="h-sub">上行 / 下行帧 · 实时镜像</div>
          </div>
          <button className="icon-btn" onClick={() => setDebug([])}>
            清空
          </button>
        </div>
        <div className="col-body">
          <DebugPanel frames={debug} />
        </div>
      </div>

      {showNew && (
        <NewAppDialog
          onClose={() => setShowNew(false)}
          onCreated={async (id) => {
            setShowNew(false);
            await refreshApps();
            setView({ type: "edit", appId: id });
          }}
        />
      )}
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/app/:appId" element={<StandalonePage />} />
      <Route path="/chat" element={<ChatPage />} />
      <Route path="*" element={<Workbench />} />
    </Routes>
  );
}
