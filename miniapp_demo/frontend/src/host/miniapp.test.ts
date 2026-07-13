import { readFileSync } from "node:fs";
import vm from "node:vm";

import { describe, expect, it, vi } from "vitest";

interface PostedMessage {
  source: string;
  frame: Record<string, unknown>;
}

function loadSdk() {
  const source = readFileSync(
    new URL("../../../sdk/miniapp.js", import.meta.url),
    "utf8",
  );
  const posted: PostedMessage[] = [];
  let receive: ((event: { data: unknown }) => void) | undefined;
  const windowObject: Record<string, unknown> = {
    location: { search: "" },
    addEventListener: vi.fn((_type: string, listener: typeof receive) => {
      receive = listener;
    }),
  };
  const context = vm.createContext({
    window: windowObject,
    parent: {
      postMessage(message: PostedMessage) {
        posted.push(message);
      },
    },
    document: {
      documentElement: { setAttribute: vi.fn() },
    },
    URLSearchParams,
    Math,
    FormData,
    fetch,
    setTimeout(callback: () => void) {
      callback();
      return 0;
    },
  });
  vm.runInContext(source, context);
  return {
    miniapp: windowObject.miniapp as {
      onInit(callback: (message: string) => void): void;
    },
    posted,
    receive(frame: unknown) {
      receive?.({ data: { source: "miniapp-host", frame } });
    },
  };
}

describe("miniapp SDK initialization", () => {
  it("assigns a usable requestId to app.init", () => {
    const sdk = loadSdk();

    expect(sdk.posted[0]).toMatchObject({
      source: "miniapp",
      frame: { data_type: "app.init" },
    });
    expect(sdk.posted[0]?.frame.requestId).toMatch(/^req_[a-z0-9]+$/);
  });

  it("dispatches app.resource on_init messages to registered handlers", () => {
    const sdk = loadSdk();
    const onInit = vi.fn();
    sdk.miniapp.onInit(onInit);

    sdk.receive({
      data_type: "app.resource",
      data: {
        app: {
          id: "fortune-teller",
          on_init: { user_message: "开始吧" },
        },
      },
    });

    expect(onInit).toHaveBeenCalledWith("开始吧");
  });
});
