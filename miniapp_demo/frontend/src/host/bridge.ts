import type { DebugFrame } from "../types";

/**
 * 客户端运行时(Host Bridge)。
 *
 * - 监听小程序 iframe 的 postMessage(source: "oneagent"),注入当前 appId 后转发到 WS 引擎。
 * - 把 WS 下行 app.resource / app.event 通过 postMessage 回传给 iframe(source: "oneagent-host")。
 * - 所有由后端镜像下来的 debug 帧交给 onDebug 回调渲染。
 */
export class HostBridge {
  private send: (frame: any) => void;
  private onDebug: (f: DebugFrame) => void;
  private appId: string | null = null;
  private iframe: HTMLIFrameElement | null = null;
  private listener: (e: MessageEvent) => void;

  constructor(send: (frame: any) => void, onDebug: (f: DebugFrame) => void) {
    this.send = send;
    this.onDebug = onDebug;
    this.listener = (e: MessageEvent) => this.handleIframeMessage(e);
    window.addEventListener("message", this.listener);
  }

  dispose() {
    window.removeEventListener("message", this.listener);
  }

  setApp(appId: string | null) {
    this.appId = appId;
  }

  setIframe(iframe: HTMLIFrameElement | null) {
    this.iframe = iframe;
  }

  /** WS 下行帧 -> 分发。 */
  handleDownFrame(frame: any) {
    if (!frame) return;
    if (frame.data_type === "debug") {
      this.onDebug(frame as DebugFrame);
      return;
    }
    if (frame.data_type === "app.resource" || frame.data_type === "app.event") {
      this.toIframe(frame);
    }
  }

  private toIframe(frame: any) {
    this.iframe?.contentWindow?.postMessage({ source: "oneagent-host", frame }, "*");
  }

  private handleIframeMessage(e: MessageEvent) {
    const msg = e.data;
    if (!msg || msg.source !== "oneagent" || !msg.frame) return;
    if (!this.appId) return;
    const frame = { ...msg.frame, appId: this.appId };
    this.send(frame);
  }
}
