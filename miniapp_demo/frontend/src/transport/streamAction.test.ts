import { afterEach, describe, expect, it, vi } from "vitest";

import type { ActionFrame, DownFrame } from "../types";
import { cancelAction, streamAction } from "./streamAction";

const encoder = new TextEncoder();

const action: ActionFrame = {
  data_type: "app.call",
  requestId: "request-1",
  appId: "fortune-teller",
  sessionId: "session-1",
  name: "draw",
  args: { count: 1 },
};

function event(
  type: string,
  seq?: number,
  requestId = action.requestId,
): DownFrame {
  return {
    data_type: "app.event",
    data: {
      type,
      requestId,
      ...(seq === undefined ? {} : { seq }),
      payload: type === "done" ? { status: "success" } : { delta: type },
    },
  };
}

function responseFromChunks(
  chunks: Uint8Array[],
  options: { contentType?: string; onCancel?: () => void } = {},
): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk);
      controller.close();
    },
    cancel() {
      options.onCancel?.();
    },
  });
  return new Response(stream, {
    headers: {
      "content-type": options.contentType ?? "text/event-stream; charset=utf-8",
    },
  });
}

function sse(...frames: unknown[]): Uint8Array {
  return encoder.encode(
    frames.map((frame) => `data: ${JSON.stringify(frame)}\n\n`).join(""),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("streamAction", () => {
  it("POSTs the complete action frame with JSON headers and signal", async () => {
    const signal = new AbortController().signal;
    const fetchMock = vi.fn().mockResolvedValue(
      responseFromChunks([sse(event("done", 0))]),
    );
    vi.stubGlobal("fetch", fetchMock);

    await streamAction(action, vi.fn(), signal);

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledWith("/api/runtime/actions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(action),
      signal,
    });
  });

  it("parses arbitrary chunks, CRLF, comments, other fields, and multiple events", async () => {
    const first = event("text", 0);
    const done = event("done", 1);
    const wire = [
      ": heartbeat\r\n",
      "event: runtime\r\n",
      `data: ${JSON.stringify(first)}\r\n\r\n`,
      "id: ignored\n",
      `data: ${JSON.stringify(done)}\n\n`,
    ].join("");
    const bytes = encoder.encode(wire);
    const chunks = Array.from(bytes, (byte) => Uint8Array.of(byte));
    const onEvent = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(responseFromChunks(chunks)),
    );

    await streamAction(action, onEvent);

    expect(onEvent.mock.calls.map(([frame]) => frame)).toEqual([first, done]);
  });

  it("supports lone CR and split CRLF without treating LF as another line", async () => {
    const first = event("text", 0);
    const done = event("done", 1);
    const doneJson = JSON.stringify(done);
    const splitAt = doneJson.indexOf('"data_type"') + '"data_type":'.length;
    const pieces = [
      `data: ${JSON.stringify(first)}\r\r`,
      `data: ${doneJson.slice(0, splitAt)}\r`,
      `\ndata: ${doneJson.slice(splitAt)}\r`,
      "\n\r",
      "\n",
    ];
    const onEvent = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          responseFromChunks(pieces.map((piece) => encoder.encode(piece))),
        ),
    );

    await streamAction(action, onEvent);

    expect(onEvent.mock.calls.map(([frame]) => frame)).toEqual([first, done]);
  });

  it("preserves UTF-8 characters split across chunks and joins multiline data", async () => {
    const text = event("你好🌟", 0);
    const textJson = JSON.stringify(text);
    const splitAt = textJson.indexOf('"data_type"') + '"data_type":'.length;
    const wire =
      `data: ${textJson.slice(0, splitAt)}\n` +
      `data: ${textJson.slice(splitAt)}\n\n` +
      `data: ${JSON.stringify(event("done", 1))}\n\n`;
    const bytes = encoder.encode(wire);
    const emojiStart = wire.indexOf("🌟");
    const byteBoundary = encoder.encode(wire.slice(0, emojiStart)).length + 2;
    const onEvent = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          responseFromChunks([
            bytes.slice(0, byteBoundary),
            bytes.slice(byteBoundary),
          ]),
        ),
    );

    await streamAction(action, onEvent);

    expect(onEvent.mock.calls.map(([frame]) => frame)).toEqual([
      text,
      event("done", 1),
    ]);
  });

  it("allows unsequenced resource frames and drops duplicate or older seq frames", async () => {
    const resource = {
      data_type: "app.resource",
      data: {
        requestId: action.requestId,
        appId: action.appId,
        appSession: "session-1",
        app: {
          id: action.appId,
          name: "Fortune",
          version: "1",
          futureAppField: "accepted",
        },
        resource: {
          uri: "/apps/fortune/ui",
          mimeType: "text/html",
          futureResourceField: true,
        },
        futureDataField: { accepted: true },
      },
    };
    const frames = [
      resource,
      event("first", 2),
      event("duplicate", 2),
      event("older", 1),
      event("done", 3),
    ];
    const onEvent = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(responseFromChunks([sse(...frames)])),
    );

    await streamAction(action, onEvent);

    expect(onEvent.mock.calls.map(([frame]) => frame)).toEqual([
      resource,
      frames[1],
      frames[4],
    ]);
  });

  it.each([
    [
      "appSession",
      {
        requestId: action.requestId,
        appId: action.appId,
        app: { id: action.appId, name: "Fortune", version: "1" },
        resource: { uri: "/ui", mimeType: "text/html" },
      },
      /appSession/i,
    ],
    [
      "appId",
      {
        requestId: action.requestId,
        appSession: "session-1",
        app: { id: action.appId, name: "Fortune", version: "1" },
        resource: { uri: "/ui", mimeType: "text/html" },
      },
      /appId/i,
    ],
    [
      "app.version",
      {
        requestId: action.requestId,
        appId: action.appId,
        appSession: "session-1",
        app: { id: action.appId, name: "Fortune" },
        resource: { uri: "/ui", mimeType: "text/html" },
      },
      /app\.version/i,
    ],
    [
      "resource.uri",
      {
        requestId: action.requestId,
        appId: action.appId,
        appSession: "session-1",
        app: { id: action.appId, name: "Fortune", version: "1" },
        resource: { mimeType: "text/html" },
      },
      /resource\.uri/i,
    ],
    [
      "resource.mimeType",
      {
        requestId: action.requestId,
        appId: action.appId,
        appSession: "session-1",
        app: { id: action.appId, name: "Fortune", version: "1" },
        resource: { uri: "/ui" },
      },
      /resource\.mimeType/i,
    ],
    [
      "string app.id",
      {
        requestId: action.requestId,
        appId: action.appId,
        appSession: "session-1",
        app: { id: 42, name: "Fortune", version: "1" },
        resource: { uri: "/ui", mimeType: "text/html" },
      },
      /app\.id/i,
    ],
    [
      "resource object",
      {
        requestId: action.requestId,
        appId: action.appId,
        appSession: "session-1",
        app: { id: action.appId, name: "Fortune", version: "1" },
        resource: "/ui",
      },
      /data\.resource.*object/i,
    ],
  ])("rejects app.resource with invalid %s", async (_name, data, error) => {
    const invalidResource = { data_type: "app.resource", data };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(responseFromChunks([sse(invalidResource)])),
    );

    await expect(streamAction(action, vi.fn())).rejects.toThrow(error);
  });

  it("cancels and releases the reader immediately after done", async () => {
    let cancelled = false;
    const trailing = event("trailing", 2);
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(sse(event("done", 1), trailing));
      },
      cancel() {
        cancelled = true;
      },
    });
    const response = new Response(stream, {
      headers: { "content-type": "text/event-stream" },
    });
    const onEvent = vi.fn();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));

    await streamAction(action, onEvent);

    expect(onEvent).toHaveBeenCalledTimes(1);
    expect(onEvent).toHaveBeenCalledWith(event("done", 1));
    expect(cancelled).toBe(true);
    expect(response.body?.locked).toBe(false);
  });

  it.each([
    [
      "HTTP status",
      new Response("bad", { status: 503, statusText: "Unavailable" }),
      /HTTP 503.*Unavailable/,
    ],
    [
      "missing body",
      new Response(null, {
        headers: { "content-type": "text/event-stream" },
      }),
      /response body/i,
    ],
    [
      "content type",
      new Response("{}", {
        headers: { "content-type": "application/json" },
      }),
      /content-type.*text\/event-stream/i,
    ],
  ])("rejects an invalid %s response", async (_name, response, error) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));

    await expect(streamAction(action, vi.fn())).rejects.toThrow(error);
  });

  it.each([
    ["invalid JSON", "data: {not-json}\n\n", /invalid JSON/i],
    ["non-object frame", "data: null\n\n", /event frame.*object/i],
    [
      "missing data object",
      'data: {"data_type":"app.event"}\n\n',
      /event frame.*data/i,
    ],
    [
      "missing requestId",
      'data: {"data_type":"app.event","data":{"type":"done"}}\n\n',
      /requestId/i,
    ],
    [
      "mismatched requestId",
      `data: ${JSON.stringify(event("done", 0, "other-request"))}\n\n`,
      /requestId.*other-request.*request-1/i,
    ],
    [
      "invalid seq",
      `data: ${JSON.stringify({
        ...event("done"),
        data: { ...event("done").data, seq: -1 },
      })}\n\n`,
      /seq.*non-negative integer/i,
    ],
  ])("rejects %s", async (_name, wire, error) => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(responseFromChunks([encoder.encode(wire as string)])),
    );

    await expect(streamAction(action, vi.fn())).rejects.toThrow(error);
  });

  it.each([
    ["array payload", { payload: [] }, /payload.*JSON object/i],
    ["string ts", { ts: "now" }, /ts.*finite number/i],
    ["numeric appId", { appId: 42 }, /appId.*string/i],
    ["boolean appSession", { appSession: false }, /appSession.*string/i],
  ])("rejects an event with %s", async (_name, override, error) => {
    const invalidEvent = {
      data_type: "app.event",
      data: {
        type: "done",
        requestId: action.requestId,
        seq: 0,
        payload: { status: "success" },
        ...override,
      },
    };
    const onEvent = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(responseFromChunks([sse(invalidEvent)])),
    );

    await expect(streamAction(action, onEvent)).rejects.toThrow(error);
    expect(onEvent).not.toHaveBeenCalled();
  });

  it("rejects a non-finite event seq before invoking the callback", async () => {
    const wire =
      `data: {"data_type":"app.event","data":{"type":"done",` +
      `"requestId":"${action.requestId}","seq":1e400}}\n\n`;
    const onEvent = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(responseFromChunks([encoder.encode(wire)])),
    );

    await expect(streamAction(action, onEvent)).rejects.toThrow(
      /seq.*finite non-negative integer/i,
    );
    expect(onEvent).not.toHaveBeenCalled();
  });

  it("rejects EOF before a done frame", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(responseFromChunks([sse(event("text", 0))])),
    );

    await expect(streamAction(action, vi.fn())).rejects.toThrow(
      /ended before.*done/i,
    );
  });

  it("propagates abort and releases the reader", async () => {
    const abortController = new AbortController();
    let stream: ReadableStream<Uint8Array>;
    const fetchMock = vi.fn((_url: string, init: RequestInit) => {
      stream = new ReadableStream<Uint8Array>({
        start(controller) {
          init.signal?.addEventListener("abort", () => {
            controller.error(
              init.signal?.reason ??
                new DOMException("The operation was aborted", "AbortError"),
            );
          });
        },
      });
      return Promise.resolve(
        new Response(stream, {
          headers: { "content-type": "text/event-stream" },
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = streamAction(action, vi.fn(), abortController.signal);
    abortController.abort(
      new DOMException("The operation was aborted", "AbortError"),
    );

    await expect(result).rejects.toMatchObject({ name: "AbortError" });
    expect(fetchMock.mock.calls[0]?.[1]?.signal).toBe(abortController.signal);
    expect(stream!.locked).toBe(false);
  });
});

describe("cancelAction", () => {
  it("POSTs to the request-specific cancel endpoint", async () => {
    const signal = new AbortController().signal;
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await cancelAction("request/with spaces", signal);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/runtime/actions/request%2Fwith%20spaces/cancel",
      { method: "POST", signal },
    );
  });

  it("rejects unsuccessful cancel responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("bad", { status: 409, statusText: "Conflict" }),
      ),
    );

    await expect(cancelAction("request-1")).rejects.toThrow(
      /cancel.*HTTP 409.*Conflict/i,
    );
  });
});
