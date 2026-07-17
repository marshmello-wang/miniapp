// @vitest-environment jsdom

import { act, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConversationBridge } from "./conversationBridge";

(globalThis as typeof globalThis & {
  IS_REACT_ACT_ENVIRONMENT: boolean;
}).IS_REACT_ACT_ENVIRONMENT = true;

const submitActionMock = vi.fn(
  async (_conversationId: string, _body: unknown) => ({}),
);

vi.mock("../conversations/actionClient", () => ({
  submitAction: (conversationId: string, body: unknown) =>
    submitActionMock(conversationId, body),
  submitSnapshot: vi.fn(),
  cancelAction: vi.fn(),
}));

afterEach(() => {
  vi.restoreAllMocks();
  submitActionMock.mockReset();
  document.body.innerHTML = "";
});

describe("ConversationBridge", () => {
  it("handles app.init by delivering app.resource", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        data_type: "app.resource",
        data: {
          app: { id: "fortune-teller", on_init: { user_message: "开始" } },
        },
      }),
    } as Response);

    const container = document.createElement("div");
    document.body.appendChild(container);
    const iframe = document.createElement("iframe");
    container.appendChild(iframe);
    const target = iframe.contentWindow!;
    const posted: unknown[] = [];
    vi.spyOn(target, "postMessage").mockImplementation((msg) => {
      posted.push(msg);
    });

    const bridge = new ConversationBridge({
      conversationId: "dev__fortune-teller",
      skillId: "fortune-teller",
      uiInstanceId: "ui_fortune-teller_dev",
      onDebug: () => {},
      getRevision: () => 0,
      setRevision: () => {},
    });
    bridge.setIframe(iframe);

    await act(async () => {
      window.dispatchEvent(
        new MessageEvent("message", {
          source: target,
          data: {
            source: "miniapp",
            frame: { data_type: "app.init", requestId: "req-init" },
          },
        }),
      );
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/apps/fortune-teller/enter",
      { method: "POST" },
    );
    expect(posted.some((msg) => {
      const frame = (msg as { frame?: { data_type?: string } }).frame;
      return frame?.data_type === "app.resource";
    })).toBe(true);

    bridge.dispose();
    fetchMock.mockRestore();
  });
});
