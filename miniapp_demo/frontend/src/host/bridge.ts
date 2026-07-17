import { cancelAction, streamAction } from "../transport/streamAction";
import type {
  ActionFrame,
  DebugFrame,
  DebugPayload,
  DownFrame,
  JsonValue,
} from "../types";

/** Host 端 iframe bridge：每个 action 使用独立 HTTP SSE 请求。 */
export class HostBridge {
  private readonly onDebug: (frame: DebugFrame) => void;
  private appId: string | null = null;
  private sessionId: string | null = null;
  private iframe: HTMLIFrameElement | null = null;
  private readonly listener: (event: MessageEvent) => void;
  private pendingUp: Array<{ frame: IframeFrame; target: WindowProxy }> = [];
  private readonly controllers = new Set<AbortController>();
  private readonly active = new Map<string, RequestContext>();
  private disposed = false;

  constructor(onDebug: (frame: DebugFrame) => void) {
    this.onDebug = onDebug;
    this.listener = (event: MessageEvent) => this.handleIframeMessage(event);
    window.addEventListener("message", this.listener);
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    window.removeEventListener("message", this.listener);
    this.pendingUp = [];
    this.abortAll();
  }

  setApp(appId: string | null, sessionId?: string | null) {
    const nextSessionId = sessionId ?? null;
    const replacesExistingApp =
      this.appId !== null &&
      (this.appId !== appId || this.sessionId !== nextSessionId);
    if (replacesExistingApp || (appId === null && this.appId !== null)) {
      this.pendingUp = [];
      this.abortAll();
    }
    this.appId = appId;
    this.sessionId = nextSessionId;
    this.flushPending();
  }

  setIframe(iframe: HTMLIFrameElement | null) {
    if (this.iframe && this.iframe !== iframe) {
      this.pendingUp = [];
      this.abortAll();
    }
    this.iframe = iframe;
  }

  private flushPending() {
    if (!this.appId || this.pendingUp.length === 0) return;
    const pending = this.pendingUp;
    this.pendingUp = [];
    for (const item of pending) {
      if (item.target === this.iframe?.contentWindow) {
        this.dispatch(item.frame, item.target);
      }
    }
  }

  private debug(dir: DebugFrame["dir"], frame: DebugPayload) {
    this.onDebug({ data_type: "debug", dir, ts: Date.now(), frame });
  }

  private handleIframeMessage(event: MessageEvent) {
    const message = event.data;
    const target = this.iframe?.contentWindow;
    if (
      !isRecord(message) ||
      message.source !== "miniapp" ||
      !isIframeFrame(message.frame) ||
      !target ||
      event.source !== target
    ) {
      return;
    }
    if (!this.appId && message.frame.data_type !== "cancel") {
      this.pendingUp.push({ frame: message.frame, target });
      return;
    }
    this.dispatch(message.frame, target);
  }

  private dispatch(frame: IframeFrame, target: WindowProxy) {
    if (frame.data_type === "cancel") {
      this.debug("up", { ...frame });
      void this.cancel(frame.requestId);
      return;
    }
    if (!this.appId) {
      this.pendingUp.push({ frame, target });
      return;
    }

    const action = {
      ...frame,
      appId: this.appId,
      ...(this.sessionId ? { sessionId: this.sessionId } : {}),
    } as ActionFrame;
    this.debug("up", { ...action });

    this.active.get(action.requestId)?.controller.abort();
    const context: RequestContext = {
      controller: new AbortController(),
      target,
      appId: this.appId,
      sessionId: this.sessionId,
    };
    this.active.set(action.requestId, context);
    this.controllers.add(context.controller);
    void this.runAction(action, context);
  }

  private async runAction(action: ActionFrame, context: RequestContext) {
    try {
      await streamAction(
        action,
        (frame) => {
          if (this.isCurrent(action.requestId, context)) {
            this.deliver(frame, context.target);
          }
        },
        context.controller.signal,
      );
    } catch (error) {
      if (
        !context.controller.signal.aborted &&
        this.isCurrent(action.requestId, context)
      ) {
        this.deliver(errorDone(action.requestId, error), context.target);
      }
    } finally {
      this.controllers.delete(context.controller);
      if (this.active.get(action.requestId) === context) {
        this.active.delete(action.requestId);
      }
    }
  }

  private async cancel(requestId: string) {
    const controller = new AbortController();
    this.controllers.add(controller);
    try {
      await cancelAction(requestId, controller.signal);
    } catch (error) {
      if (!controller.signal.aborted) {
        const context = this.active.get(requestId);
        if (context && this.isCurrent(requestId, context)) {
          this.deliver(errorDone(requestId, error), context.target);
        }
      }
    } finally {
      this.controllers.delete(controller);
    }
  }

  /** 从外部注入一个 DownFrame 到 iframe（用于 chat 流转发 ui_update）。 */
  injectDown(frame: DownFrame) {
    const target = this.iframe?.contentWindow;
    if (target) {
      this.deliver(frame, target);
    }
  }

  private deliver(frame: DownFrame, target: WindowProxy) {
    this.debug("down", frame as unknown as DebugPayload);
    target.postMessage({ source: "miniapp-host", frame }, "*");
  }

  private isCurrent(requestId: string, context: RequestContext) {
    return (
      !this.disposed &&
      this.active.get(requestId) === context &&
      this.appId === context.appId &&
      this.sessionId === context.sessionId &&
      this.iframe?.contentWindow === context.target
    );
  }

  private abortAll() {
    for (const controller of this.controllers) controller.abort();
    this.controllers.clear();
    this.active.clear();
  }
}

interface CancelFrame {
  data_type: "cancel";
  requestId: string;
}

type IframeFrame = ActionFrame | CancelFrame;

interface RequestContext {
  controller: AbortController;
  target: WindowProxy;
  appId: string;
  sessionId: string | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isIframeFrame(value: unknown): value is IframeFrame {
  if (!isRecord(value)) return false;
  if (typeof value.requestId !== "string" || value.requestId.length === 0) {
    return false;
  }
  return (
    value.data_type === "app.init" ||
    value.data_type === "app.call" ||
    value.data_type === "app.agent" ||
    value.data_type === "cancel"
  );
}

function errorDone(requestId: string, error: unknown): DownFrame {
  const message = error instanceof Error ? error.message : String(error);
  return {
    data_type: "app.event",
    data: {
      type: "done",
      requestId,
      payload: {
        status: "error",
        error: message,
      } satisfies Record<string, JsonValue>,
    },
  };
}
