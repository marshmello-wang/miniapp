import type { DurableEvent } from "./types";

function parseEvent(data: string): DurableEvent {
  const parsed = JSON.parse(data) as DurableEvent;
  if (
    typeof parsed.eventId !== "string" ||
    typeof parsed.conversationSeq !== "number" ||
    typeof parsed.type !== "string"
  ) {
    throw new Error("Invalid durable event frame");
  }
  return parsed;
}

export class ConversationEventStream {
  private controller: AbortController | null = null;
  private lastSeq = 0;
  private seenIds = new Set<string>();

  constructor(
    private readonly conversationId: string,
    private readonly onEvent: (event: DurableEvent) => void,
    private readonly onError?: (error: Error) => void,
  ) {}

  start(after = 0) {
    this.stop();
    this.lastSeq = after;
    this.controller = new AbortController();
    void this.run(this.controller.signal, after);
  }

  stop() {
    this.controller?.abort();
    this.controller = null;
  }

  getLastSeq() {
    return this.lastSeq;
  }

  private async run(signal: AbortSignal, after: number) {
    try {
      const response = await fetch(
        `/api/conversations/${encodeURIComponent(this.conversationId)}/events?after=${after}`,
        { headers: { Accept: "text/event-stream" }, signal },
      );
      if (!response.ok || !response.body) {
        throw new Error(`SSE failed: HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (!signal.aborted) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let boundary = buffer.indexOf("\n\n");
        while (boundary !== -1) {
          const chunk = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          this.consumeChunk(chunk);
          boundary = buffer.indexOf("\n\n");
        }
      }
    } catch (error) {
      if (signal.aborted) return;
      this.onError?.(error instanceof Error ? error : new Error(String(error)));
    }
  }

  private consumeChunk(chunk: string) {
    const dataLine = chunk
      .split("\n")
      .find((line) => line.startsWith("data: "));
    if (!dataLine) return;

    const event = parseEvent(dataLine.slice(6));
    if (this.seenIds.has(event.eventId)) return;
    this.seenIds.add(event.eventId);
    if (event.conversationSeq > this.lastSeq) {
      this.lastSeq = event.conversationSeq;
    }
    this.onEvent(event);
  }
}
