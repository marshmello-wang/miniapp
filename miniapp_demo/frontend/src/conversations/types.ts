import type { JsonValue } from "../types";

export type ActionKind = "agent" | "direct";
export type ActionSource = "chat" | "ui";

export interface SubmitActionRequest {
  actionId: string;
  kind: ActionKind;
  source: ActionSource;
  intent?: string;
  name?: string;
  args?: Record<string, JsonValue>;
  skillId?: string;
  uiInstanceId?: string;
  expectedRevision?: number;
}

export interface ViewSnapshotPayload {
  snapshotRequestId: string;
  uiInstanceId: string;
  skillId: string;
  route?: string;
  revision?: number;
  env: Record<string, JsonValue>;
}

export interface DurableEvent {
  eventId: string;
  conversationId: string;
  conversationSeq: number;
  actionId?: string;
  actor: "user" | "agent" | "tool" | "runtime";
  type: string;
  skillId?: string;
  uiInstanceId?: string;
  ts: number;
  payload: Record<string, JsonValue>;
}
