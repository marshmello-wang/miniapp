import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { ensureMicPermission } from "../host/permissions";
import type { AppManifest } from "../types";

interface Props {
  appId: string;
  onIframe: (el: HTMLIFrameElement | null) => void;
  onEdit: () => void;
}

type Device = "desktop" | "mobile";

const MOBILE_PRESETS = [
  { label: "iPhone 15", w: 393, h: 852 },
  { label: "iPhone SE", w: 375, h: 667 },
  { label: "Pixel 8", w: 412, h: 915 },
  { label: "小屏", w: 360, h: 640 },
];

export function AppFrame({ appId, onIframe, onEdit }: Props) {
  const [manifest, setManifest] = useState<AppManifest | null>(null);
  const [device, setDevice] = useState<Device>("desktop");
  const [presetIdx, setPresetIdx] = useState(0);
  const [landscape, setLandscape] = useState(false);

  useEffect(() => {
    setManifest(null);
    api.manifest(appId).then(setManifest).catch(() => setManifest(null));
  }, [appId]);

  // 框架统一申请麦克风权限:仅当小程序声明需要,且整个 origin 只申请一次。
  const needsMic = !!manifest?.permissions?.includes("microphone");
  useEffect(() => {
    if (needsMic) void ensureMicPermission();
  }, [needsMic]);
  const allow = needsMic ? "microphone" : undefined;

  const preset = MOBILE_PRESETS[presetIdx];
  const vw = landscape ? preset.h : preset.w;
  const vh = landscape ? preset.w : preset.h;

  // 按设备挑选入口文件:优先专属入口,否则回退到默认(响应式)入口。
  const src = useMemo(() => {
    const entries = manifest?.entries;
    let file = entries?.default || "index.html";
    if (device === "mobile" && entries?.mobile) file = entries.mobile;
    if (device === "desktop" && entries?.desktop) file = entries.desktop;
    return `/api/apps/${appId}/ui/${file}?device=${device}`;
  }, [appId, manifest, device]);

  const hasDedicated =
    (device === "mobile" && manifest?.entries?.mobile) ||
    (device === "desktop" && manifest?.entries?.desktop);

  return (
    <div className="frame-wrap">
      <div className="frame-toolbar">
        <span className="t-title">{manifest?.name || appId}</span>
        <span className="t-sub">· {hasDedicated ? "专属入口" : "响应式"}</span>

        <div className="seg" role="tablist" aria-label="设备">
          <button className={device === "desktop" ? "on" : ""} onClick={() => setDevice("desktop")}>
            桌面
          </button>
          <button className={device === "mobile" ? "on" : ""} onClick={() => setDevice("mobile")}>
            移动
          </button>
        </div>

        {device === "mobile" && (
          <>
            <select
              className="seg-select"
              value={presetIdx}
              onChange={(e) => setPresetIdx(Number(e.target.value))}
              title="机型尺寸"
            >
              {MOBILE_PRESETS.map((p, i) => (
                <option key={p.label} value={i}>
                  {p.label} · {p.w}×{p.h}
                </option>
              ))}
            </select>
            <button
              className="btn"
              title={landscape ? "切回竖屏" : "切换横屏"}
              onClick={() => setLandscape((v) => !v)}
            >
              ⟳ {landscape ? "竖屏" : "横屏"}
            </button>
          </>
        )}

        <button className="btn" style={{ marginLeft: "auto" }} onClick={onEdit}>
          编辑技能文件
        </button>
      </div>

      {device === "desktop" ? (
        <div className="stage stage-desktop">
          <iframe
            key={`${appId}-desktop`}
            ref={onIframe}
            className="frame-host"
            src={src}
            title={appId}
            allow={allow}
          />
        </div>
      ) : (
        <div className="stage stage-mobile">
          <div className={`device-phone ${landscape ? "landscape" : ""}`} style={{ width: vw, height: vh }}>
            <div className="device-notch" />
            <iframe
              key={`${appId}-mobile-${presetIdx}`}
              ref={onIframe}
              className="phone-screen"
              src={src}
              title={appId}
              allow={allow}
            />
          </div>
        </div>
      )}
    </div>
  );
}
