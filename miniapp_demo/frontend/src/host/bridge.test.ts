import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AppCallActionFrame, DebugFrame, DownFrame } from "../types";
import { HostBridge } from "./bridge";

const streamAction = vi.fn<
  (frame: AppCallActionFrame, onEvent: (frame: DownFrame) => void, signal?: AbortSignal) => Promise<void>
>();
const cancelAction = vi.fn<(requestId: string, signal?: AbortSignal) => Promise<void>>();

vi.mock("../transport/streamAction", () => ({
  streamAction: (...args: Parameters<typeof streamAction>) => streamAction(...args),
  cancelAction: (...args: Parameters<typeof cancelAction>) => cancelAction(...args),
}));

type MessageListener = (event: MessageEvent) => void;

function action(requestId = "req-1"): Omit<AppCallActionFrame, "appId"> {
  return {
    data_type: "app.call",
    requestId,
    name: "draw",
    args: { count: 1 },
  };
}

function done(requestId = "req-1"): DownFrame {
  return {
    data_type: "app.event",
    data: {
      type: "done",
      requestId,
      payload: { status: "success" },
    },
  };
}

function iframe() {
  const contentWindow = { postMessage: vi.fn() };
  return {
    element: { contentWindow } as unknown as HTMLIFrameElement,
    contentWindow,
  };
}

describe("HostBridge", () => {
  let listener: MessageListener | undefined;
  let removeEventListener: ReturnType<typeof vi.fn>;
  let onDebug: ReturnType<typeof vi.fn<(frame: DebugFrame) => void>>;

  beforeEach(() => {
    streamAction.mockReset();
    cancelAction.mockReset();
    streamAction.mockResolvedValue();
    cancelAction.mockResolvedValue();
    removeEventListener = vi.fn();
    vi.stubGlobal("window", {
      addEventListener: vi.fn((_type: string, next: MessageListener) => {
        listener = next;
      }),
      removeEventListener,
    });
    onDebug = vi.fn();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function post(frame: unknown, source: WindowProxy) {
    listener?.({ data: { source: "miniapp", frame }, source } as MessageEvent);
  }

  it("queues actions until an app is set, then injects app and session IDs", async () => {
    const target = iframe();
    const bridge = new HostBridge(onDebug);
    bridge.setIframe(target.element);

    post(action(), target.contentWindow as unknown as WindowProxy);
    expect(streamAction).not.toHaveBeenCalled();

    bridge.setApp("fortune-teller", "session-1");
    await vi.waitFor(() => expect(streamAction).toHaveBeenCalledOnce());
    expect(streamAction.mock.calls[0]?.[0]).toEqual({
      ...action(),
      appId: "fortune-teller",
      sessionId: "session-1",
    });
  });

  it("records local up/down debug frames and streams responses to the initiating iframe", async () => {
    const target = iframe();
    streamAction.mockImplementation(async (_frame, onEvent) => {
      onEvent(done());
    });
    const bridge = new HostBridge(onDebug);
    bridge.setApp("fortune-teller");
    bridge.setIframe(target.element);

    post(action(), target.contentWindow as unknown as WindowProxy);
    await vi.waitFor(() => expect(target.contentWindow.postMessage).toHaveBeenCalledOnce());

    expect(onDebug.mock.calls.map(([frame]) => frame.dir)).toEqual(["up", "down"]);
    expect(onDebug.mock.calls[0]?.[0].frame).toMatchObject({
      data_type: "app.call",
      appId: "fortune-teller",
    });
    expect(onDebug.mock.calls[1]?.[0].frame).toEqual(done());
    expect(target.contentWindow.postMessage).toHaveBeenCalledWith(
      { source: "miniapp-host", frame: done() },
      "*",
    );
  });

  it("isolates old streams when the app or iframe changes", async () => {
    const first = iframe();
    const second = iframe();
    let emit: ((frame: DownFrame) => void) | undefined;
    let signal: AbortSignal | undefined;
    streamAction.mockImplementation(async (_frame, onEvent, currentSignal) => {
      emit = onEvent;
      signal = currentSignal;
      await new Promise<void>(() => {});
    });
    const bridge = new HostBridge(onDebug);
    bridge.setApp("first");
    bridge.setIframe(first.element);

    post(action(), first.contentWindow as unknown as WindowProxy);
    await vi.waitFor(() => expect(streamAction).toHaveBeenCalledOnce());
    bridge.setApp("second");
    bridge.setIframe(second.element);
    expect(signal?.aborted).toBe(true);

    emit?.(done());
    expect(first.contentWindow.postMessage).not.toHaveBeenCalled();
    expect(second.contentWindow.postMessage).not.toHaveBeenCalled();
  });

  it("aborts every in-flight request and removes its listener on dispose", async () => {
    const target = iframe();
    const signals: AbortSignal[] = [];
    streamAction.mockImplementation(async (_frame, _onEvent, signal) => {
      if (signal) signals.push(signal);
      await new Promise<void>(() => {});
    });
    const bridge = new HostBridge(onDebug);
    bridge.setApp("fortune-teller");
    bridge.setIframe(target.element);
    post(action("req-1"), target.contentWindow as unknown as WindowProxy);
    post(action("req-2"), target.contentWindow as unknown as WindowProxy);
    await vi.waitFor(() => expect(streamAction).toHaveBeenCalledTimes(2));

    bridge.dispose();

    expect(signals).toHaveLength(2);
    expect(signals.every((signal) => signal.aborted)).toBe(true);
    expect(removeEventListener).toHaveBeenCalledWith("message", listener);
  });

  it("posts cancel frames to the cancel endpoint without starting another stream", async () => {
    const target = iframe();
    const bridge = new HostBridge(onDebug);
    bridge.setApp("fortune-teller");
    bridge.setIframe(target.element);

    post(
      { data_type: "cancel", requestId: "req-1" },
      target.contentWindow as unknown as WindowProxy,
    );
    await vi.waitFor(() => expect(cancelAction).toHaveBeenCalledOnce());

    expect(cancelAction.mock.calls[0]?.[0]).toBe("req-1");
    expect(streamAction).not.toHaveBeenCalled();
    expect(onDebug).toHaveBeenCalledOnce();
    expect(onDebug.mock.calls[0]?.[0]).toMatchObject({
      dir: "up",
      frame: { data_type: "cancel", requestId: "req-1" },
    });
  });

  it("sends a synthetic done(error) to the matching iframe when streaming fails", async () => {
    const target = iframe();
    streamAction.mockRejectedValue(new Error("network unavailable"));
    const bridge = new HostBridge(onDebug);
    bridge.setApp("fortune-teller");
    bridge.setIframe(target.element);

    post(action(), target.contentWindow as unknown as WindowProxy);
    await vi.waitFor(() => expect(target.contentWindow.postMessage).toHaveBeenCalledOnce());

    const message = target.contentWindow.postMessage.mock.calls[0]?.[0];
    expect(message).toMatchObject({
      source: "miniapp-host",
      frame: {
        data_type: "app.event",
        data: {
          type: "done",
          requestId: "req-1",
          payload: { status: "error", error: "network unavailable" },
        },
      },
    });
    expect(onDebug.mock.calls[onDebug.mock.calls.length - 1]?.[0]).toMatchObject({ dir: "down", frame: message.frame });
  });
});
