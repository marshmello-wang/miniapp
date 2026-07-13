// @vitest-environment jsdom

import { act, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ActionFrame, DownFrame } from "../types";
import { MiniappOverlay } from "./MiniappOverlay";

(globalThis as typeof globalThis & {
  IS_REACT_ACT_ENVIRONMENT: boolean;
}).IS_REACT_ACT_ENVIRONMENT = true;

const streamAction = vi.fn<
  (
    frame: ActionFrame,
    onEvent: (frame: DownFrame) => void,
    signal?: AbortSignal,
  ) => Promise<void>
>();

vi.mock("../transport/streamAction", () => ({
  streamAction: (...args: Parameters<typeof streamAction>) =>
    streamAction(...args),
  cancelAction: vi.fn(),
}));

afterEach(() => {
  vi.restoreAllMocks();
  streamAction.mockReset();
  document.body.innerHTML = "";
});

describe("MiniappOverlay", () => {
  it("在 StrictMode effect 重放后仍接收 iframe 的 app.init", async () => {
    streamAction.mockResolvedValue();
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    await act(async () => {
      root.render(
        <StrictMode>
          <MiniappOverlay
            appId="fortune-teller"
            sessionId="session-1"
            onClose={() => {}}
          />
        </StrictMode>,
      );
    });

    const iframe = container.querySelector("iframe");
    expect(iframe?.contentWindow).toBeTruthy();

    await act(async () => {
      window.dispatchEvent(
        new MessageEvent("message", {
          source: iframe!.contentWindow,
          data: {
            source: "miniapp",
            frame: { data_type: "app.init", requestId: "req-init" },
          },
        }),
      );
    });

    expect(streamAction).toHaveBeenCalledWith(
      {
        data_type: "app.init",
        requestId: "req-init",
        appId: "fortune-teller",
        sessionId: "session-1",
      },
      expect.any(Function),
      expect.any(AbortSignal),
    );

    await act(async () => root.unmount());
  });
});
