import type { ActionFrame, DownFrame } from "../types";

const ACTIONS_URL = "/api/runtime/actions";
const DOWN_FRAME_TYPES = new Set([
  "app.event",
  "app.resource",
  "chat.event",
]);

type EventHandler = (frame: DownFrame) => void | Promise<void>;

export async function cancelAction(
  requestId: string,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(
    `${ACTIONS_URL}/${encodeURIComponent(requestId)}/cancel`,
    { method: "POST", signal },
  );
  if (!response.ok) {
    throw new Error(
      `Runtime action cancel failed: HTTP ${response.status} ${response.statusText}`.trim(),
    );
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireNonEmptyString(
  record: Record<string, unknown>,
  field: string,
  path: string,
): void {
  if (typeof record[field] !== "string" || record[field].length === 0) {
    throw new Error(
      `Invalid SSE app.resource frame: ${path}.${field} must be a non-empty string`,
    );
  }
}

function validateAppResource(data: Record<string, unknown>): void {
  requireNonEmptyString(data, "appId", "data");
  requireNonEmptyString(data, "appSession", "data");

  if (!isRecord(data.app)) {
    throw new Error(
      "Invalid SSE app.resource frame: data.app must be an object",
    );
  }
  requireNonEmptyString(data.app, "id", "data.app");
  requireNonEmptyString(data.app, "name", "data.app");
  requireNonEmptyString(data.app, "version", "data.app");

  if (!isRecord(data.resource)) {
    throw new Error(
      "Invalid SSE app.resource frame: data.resource must be an object",
    );
  }
  requireNonEmptyString(data.resource, "uri", "data.resource");
  requireNonEmptyString(data.resource, "mimeType", "data.resource");
}

function validateEventData(data: Record<string, unknown>): void {
  if (data.payload !== undefined && !isRecord(data.payload)) {
    throw new Error(
      "Invalid SSE event frame: data.payload must be a JSON object",
    );
  }
  if (
    data.ts !== undefined &&
    (typeof data.ts !== "number" || !Number.isFinite(data.ts))
  ) {
    throw new Error("Invalid SSE event frame: data.ts must be a finite number");
  }
  if (data.appId !== undefined && typeof data.appId !== "string") {
    throw new Error("Invalid SSE event frame: data.appId must be a string");
  }
  if (data.appSession !== undefined && typeof data.appSession !== "string") {
    throw new Error("Invalid SSE event frame: data.appSession must be a string");
  }
}

function validateFrame(value: unknown, expectedRequestId: string): DownFrame {
  if (!isRecord(value)) {
    throw new Error("Invalid SSE event frame: expected an object");
  }
  if (
    typeof value.data_type !== "string" ||
    !DOWN_FRAME_TYPES.has(value.data_type)
  ) {
    throw new Error(
      `Invalid SSE event frame: unsupported data_type ${String(value.data_type)}`,
    );
  }
  if (!isRecord(value.data)) {
    throw new Error("Invalid SSE event frame: data must be an object");
  }

  const requestId = value.data.requestId;
  if (typeof requestId !== "string" || requestId.length === 0) {
    throw new Error("Invalid SSE event frame: data.requestId is required");
  }
  if (requestId !== expectedRequestId) {
    throw new Error(
      `SSE event requestId ${requestId} does not match request ${expectedRequestId}`,
    );
  }

  const seq = value.data.seq;
  if (
    seq !== undefined &&
    (typeof seq !== "number" ||
      !Number.isFinite(seq) ||
      !Number.isInteger(seq) ||
      seq < 0)
  ) {
    throw new Error(
      "Invalid SSE event frame: seq must be a finite non-negative integer",
    );
  }

  if (
    value.data_type !== "app.resource" &&
    (typeof value.data.type !== "string" || value.data.type.length === 0)
  ) {
    throw new Error("Invalid SSE event frame: data.type is required");
  }
  if (value.data_type === "app.resource") {
    validateAppResource(value.data);
  } else {
    validateEventData(value.data);
  }

  return value as unknown as DownFrame;
}

function parseJson(data: string): unknown {
  try {
    return JSON.parse(data);
  } catch (error) {
    const detail = error instanceof Error ? `: ${error.message}` : "";
    throw new Error(`Invalid JSON in SSE data${detail}`);
  }
}

function isDone(frame: DownFrame): boolean {
  return (
    (frame.data_type === "app.event" ||
      frame.data_type === "chat.event") &&
    frame.data.type === "done"
  );
}

export async function streamAction(
  frame: ActionFrame,
  onEvent: EventHandler,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(ACTIONS_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(frame),
    signal,
  });

  if (!response.ok) {
    throw new Error(
      `Runtime action request failed: HTTP ${response.status} ${response.statusText}`.trim(),
    );
  }

  const contentType = response.headers.get("content-type");
  if (
    contentType === null ||
    !/^text\/event-stream(?:\s*;|$)/i.test(contentType)
  ) {
    throw new Error(
      `Invalid runtime response content-type: expected text/event-stream, received ${contentType ?? "none"}`,
    );
  }
  if (response.body === null) {
    throw new Error("Invalid runtime response: response body is missing");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let dataLines: string[] = [];
  let highestSeq = -1;
  let done = false;
  let shouldCancel = true;

  const dispatch = async (): Promise<boolean> => {
    if (dataLines.length === 0) return false;

    const data = dataLines.join("\n");
    dataLines = [];
    const downFrame = validateFrame(parseJson(data), frame.requestId);
    const seq = downFrame.data.seq;
    if (seq !== undefined) {
      if (seq <= highestSeq) return false;
      highestSeq = seq;
    }

    await onEvent(downFrame);
    return isDone(downFrame);
  };

  const processLine = async (line: string): Promise<boolean> => {
    if (line === "") return dispatch();
    if (line.startsWith(":")) return false;

    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "data") dataLines.push(value);
    return false;
  };

  const processBuffer = async (atEof = false): Promise<boolean> => {
    while (buffer.length > 0) {
      const carriageReturn = buffer.indexOf("\r");
      const lineFeed = buffer.indexOf("\n");
      const lineEnd =
        carriageReturn === -1
          ? lineFeed
          : lineFeed === -1
            ? carriageReturn
            : Math.min(carriageReturn, lineFeed);

      if (lineEnd === -1) break;
      if (
        buffer[lineEnd] === "\r" &&
        lineEnd === buffer.length - 1 &&
        !atEof
      ) {
        break;
      }

      const line = buffer.slice(0, lineEnd);
      const separatorLength =
        buffer[lineEnd] === "\r" && buffer[lineEnd + 1] === "\n" ? 2 : 1;
      buffer = buffer.slice(lineEnd + separatorLength);
      if (await processLine(line)) return true;
    }

    if (atEof && buffer.length > 0) {
      const finalLine = buffer;
      buffer = "";
      return processLine(finalLine);
    }
    return false;
  };

  try {
    while (!done) {
      const result = await reader.read();
      if (result.done) {
        buffer += decoder.decode();
        done = await processBuffer(true);
        if (!done) {
          shouldCancel = false;
          throw new Error(
            `Runtime action stream for requestId ${frame.requestId} ended before a done event`,
          );
        }
        break;
      }

      buffer += decoder.decode(result.value, { stream: true });
      done = await processBuffer();
    }

    if (done) {
      await reader.cancel();
      shouldCancel = false;
    }
  } finally {
    if (shouldCancel) {
      try {
        await reader.cancel(signal?.reason);
      } catch {
        // Preserve the original stream, callback, or abort error.
      }
    }
    reader.releaseLock();
  }
}
