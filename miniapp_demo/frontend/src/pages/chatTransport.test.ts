import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ActionFrame, DownFrame } from "../types";
import { runChatAction } from "./chatTransport";

const streamAction = vi.fn<
  (frame: ActionFrame, onEvent: (frame: DownFrame) => void, signal?: AbortSignal) => Promise<void>
>();

vi.mock("../transport/streamAction", () => ({
  streamAction: (...args: Parameters<typeof streamAction>) => streamAction(...args),
}));

describe("runChatAction", () => {
  beforeEach(() => {
    streamAction.mockReset();
    streamAction.mockResolvedValue();
  });

  it("streams chat.send events through the supplied handler", async () => {
    const onEvent = vi.fn();
    const signal = new AbortController().signal;
    const down: DownFrame = {
      data_type: "chat.event",
      data: {
        type: "done",
        requestId: "chat-1",
        payload: { status: "success" },
      },
    };
    streamAction.mockImplementation(async (_frame, handler) => {
      handler(down);
    });

    await runChatAction(
      {
        requestId: "chat-1",
        sessionId: "session-1",
        intent: "你好",
        username: "alden",
      },
      onEvent,
      signal,
    );

    expect(streamAction).toHaveBeenCalledWith(
      {
        data_type: "chat.send",
        requestId: "chat-1",
        sessionId: "session-1",
        intent: "你好",
        username: "alden",
      },
      onEvent,
      signal,
    );
    expect(onEvent).toHaveBeenCalledWith(down);
  });

  it("propagates transport errors so the page can end streaming visibly", async () => {
    const error = new Error("offline");
    streamAction.mockRejectedValue(error);

    await expect(
      runChatAction(
        {
          requestId: "chat-1",
          sessionId: "session-1",
          intent: "你好",
        },
        vi.fn(),
      ),
    ).rejects.toBe(error);
  });
});
