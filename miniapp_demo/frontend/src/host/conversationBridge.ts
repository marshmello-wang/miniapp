import { cancelAction, submitAction, submitSnapshot } from "../conversations/actionClient";
import type { DurableEvent } from "../conversations/types";
import type { DebugFrame, DebugPayload, JsonValue } from "../types";

interface BridgeConfig {
  conversationId: string;
  skillId: string;
  uiInstanceId: string;
  onDebug: (frame: DebugFrame) => void;
  onLoadingChange?: (loading: boolean) => void;
  getRevision: () => number;
  setRevision: (revision: number) => void;
}

type IframeUpFrame =
  | { data_type: "app.init"; requestId: string }
  | { data_type: "app.call"; requestId: string; name: string; args?: Record<string, JsonValue> }
  | { data_type: "app.agent"; requestId: string; intent?: string; focus?: JsonValue }
  | { data_type: "cancel"; requestId: string };

export class ConversationBridge {
  private readonly config: BridgeConfig;
  private iframe: HTMLIFrameElement | null = null;
  private readonly listener: (event: MessageEvent) => void;
  private pendingUp: Array<{ frame: IframeUpFrame; target: WindowProxy }> = [];
  private pendingDown: Array<Record<string, unknown>> = [];
  private widgetReady = false;
  private loading = false;
  private disposed = false;

  constructor(config: BridgeConfig) {
    this.config = config;
    this.listener = (event: MessageEvent) => this.handleIframeMessage(event);
    window.addEventListener("message", this.listener);
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    window.removeEventListener("message", this.listener);
    this.pendingUp = [];
  }

  setIframe(iframe: HTMLIFrameElement | null) {
    if (iframe !== this.iframe) {
      this.widgetReady = false;
      this.pendingDown = [];
    }
    this.iframe = iframe;
    this.flushPending();
  }

  async getViewSnapshot(route = "/"): Promise<{
    snapshotRequestId: string;
    uiInstanceId: string;
    skillId: string;
    route: string;
    revision: number;
    env: Record<string, JsonValue>;
  } | null> {
    const target = this.iframe?.contentWindow;
    if (!target) return null;

    const requestId = `getEnv_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    return new Promise((resolve) => {
      const listener = (event: MessageEvent) => {
        const msg = event.data;
        if (
          event.source !== target ||
          !msg ||
          msg.source !== "miniapp" ||
          msg.type !== "env" ||
          msg.requestId !== requestId
        ) {
          return;
        }
        window.removeEventListener("message", listener);
        resolve({
          snapshotRequestId: requestId,
          uiInstanceId: this.config.uiInstanceId,
          skillId: this.config.skillId,
          route: (msg.route as string) || route,
          revision: this.config.getRevision(),
          env: (msg.env as Record<string, JsonValue>) || {},
        });
      };
      window.addEventListener("message", listener);
      target.postMessage({ source: "miniapp-host", type: "getEnv", requestId }, "*");
      window.setTimeout(() => {
        window.removeEventListener("message", listener);
        resolve(null);
      }, 500);
    });
  }

  async handleConversationEvent(event: DurableEvent) {
    if (event.uiInstanceId && event.uiInstanceId !== this.config.uiInstanceId) {
      return;
    }
    if (event.skillId && event.skillId !== this.config.skillId) {
      return;
    }

    if (event.type === "ui.loading.changed") {
      this.loading = Boolean(event.payload.loading);
      this.config.onLoadingChange?.(this.loading);
      this.deliverToIframe({ type: "host.loading", loading: this.loading });
      return;
    }

    if (event.type === "ui.snapshot.requested" && event.actionId) {
      const snapshot = await this.getViewSnapshot();
      if (!snapshot) return;
      snapshot.snapshotRequestId =
        (event.payload.snapshotRequestId as string) || snapshot.snapshotRequestId;
      await submitSnapshot(this.config.conversationId, event.actionId, snapshot);
      return;
    }

    if (event.type === "ui.command") {
      this.deliverToIframe({
        type: "host.ui_command",
        command: event.payload,
      });
      const nextRevision = event.payload.expectedRevision;
      if (typeof nextRevision === "number") {
        this.config.setRevision(nextRevision + 1);
      }
      return;
    }

    if (
      event.actionId &&
      (event.type === "agent_action.completed" ||
        event.type === "agent_action.failed" ||
        event.type === "direct_action.completed" ||
        event.type === "direct_action.failed")
    ) {
      this.deliverToIframe({
        type: "host.action.done",
        requestId: event.actionId,
        ok:
          event.type === "agent_action.completed" ||
          event.type === "direct_action.completed",
        payload: event.payload,
      });
    }
  }

  private handleIframeMessage(event: MessageEvent) {
    const message = event.data;
    const target = this.iframe?.contentWindow;
    if (
      !message ||
      message.source !== "miniapp" ||
      !message.frame ||
      !target ||
      event.source !== target
    ) {
      return;
    }
    if (!this.widgetReady) {
      this.widgetReady = true;
      this.flushPendingDown();
    }
    this.dispatch(message.frame as IframeUpFrame, target);
  }

  private dispatch(frame: IframeUpFrame, target: WindowProxy) {
    if (!this.iframe) {
      this.pendingUp.push({ frame, target });
      return;
    }

    if (frame.data_type === "cancel") {
      this.debug("up", frame);
      void cancelAction(this.config.conversationId, frame.requestId);
      return;
    }

    if (frame.data_type === "app.init") {
      this.debug("up", frame);
      void this.handleAppInit(frame.requestId);
      return;
    }

    if (frame.data_type === "app.call") {
      if (this.loading) {
        this.deliverToIframe({
          type: "host.error",
          requestId: frame.requestId,
          error: "UI locked by agent action",
        });
        return;
      }
      this.debug("up", frame);
      void submitAction(this.config.conversationId, {
        actionId: frame.requestId,
        kind: "direct",
        source: "ui",
        skillId: this.config.skillId,
        uiInstanceId: this.config.uiInstanceId,
        name: frame.name,
        args: frame.args,
        expectedRevision: this.config.getRevision(),
      }).catch((error) => {
        this.deliverToIframe({
          type: "host.error",
          requestId: frame.requestId,
          error: error instanceof Error ? error.message : String(error),
        });
      });
      return;
    }

    if (frame.data_type === "app.agent") {
      this.debug("up", frame);
      void submitAction(this.config.conversationId, {
        actionId: frame.requestId,
        kind: "agent",
        source: "ui",
        skillId: this.config.skillId,
        uiInstanceId: this.config.uiInstanceId,
        intent: frame.intent || "",
      }).catch((error) => {
        this.deliverToIframe({
          type: "host.error",
          requestId: frame.requestId,
          error: error instanceof Error ? error.message : String(error),
        });
      });
    }
  }

  private async handleAppInit(requestId: string) {
    try {
      const response = await fetch(
        `/api/apps/${encodeURIComponent(this.config.skillId)}/enter`,
        { method: "POST" },
      );
      if (!response.ok) {
        throw new Error(`enter failed: HTTP ${response.status}`);
      }
      const resource = await response.json();
      this.deliverFrame(resource);
      this.deliverFrame({
        data_type: "app.event",
        data: {
          type: "done",
          requestId,
          payload: { status: "success" },
        },
      });
    } catch (error) {
      this.deliverFrame({
        data_type: "app.event",
        data: {
          type: "done",
          requestId,
          payload: {
            status: "error",
            error: error instanceof Error ? error.message : String(error),
          },
        },
      });
    }
  }

  private deliverFrame(frame: Record<string, unknown>) {
    const target = this.iframe?.contentWindow;
    if (!target) return;
    this.debug("down", frame);
    target.postMessage({ source: "miniapp-host", frame }, "*");
  }

  private flushPending() {
    if (!this.iframe || this.pendingUp.length === 0) return;
    const pending = this.pendingUp;
    this.pendingUp = [];
    for (const item of pending) {
      if (item.target === this.iframe.contentWindow) {
        this.dispatch(item.frame, item.target);
      }
    }
  }

  private flushPendingDown() {
    if (this.pendingDown.length === 0) return;
    const pending = this.pendingDown;
    this.pendingDown = [];
    for (const payload of pending) {
      this.deliverToIframe(payload);
    }
  }

  private deliverToIframe(payload: Record<string, unknown>) {
    const target = this.iframe?.contentWindow;
    if (!target) return;
    if (!this.widgetReady) {
      this.pendingDown.push(payload);
      return;
    }
    this.debug("down", payload);
    target.postMessage({ source: "miniapp-host", ...payload }, "*");
  }

  private debug(dir: DebugFrame["dir"], frame: DebugPayload) {
    this.config.onDebug({ data_type: "debug", dir, ts: Date.now(), frame });
  }
}
