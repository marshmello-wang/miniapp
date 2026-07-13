export interface AppInfo {
  id: string;
  name: string;
  version: string;
  description: string;
  entry_ui: string;
}

export interface ScriptDef {
  name: string;
  path: string;
  visibility: string[];
}

export interface AppEntries {
  default: string;
  desktop: string | null;
  mobile: string | null;
}

export interface AppManifest {
  id: string;
  name: string;
  version: string;
  entry_ui: string;
  entries: AppEntries;
  description: string;
  scripts: ScriptDef[];
  skill: { content_file_path: string; binding_tools: string[] };
  permissions: string[];
}

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue =
  | JsonPrimitive
  | JsonValue[]
  | { [key: string]: JsonValue };

interface ActionFrameBase {
  requestId: string;
}

export interface AppInitActionFrame extends ActionFrameBase {
  data_type: "app.init";
  appId: string;
  sessionId?: string;
}

export interface AppCallActionFrame extends ActionFrameBase {
  data_type: "app.call";
  appId: string;
  sessionId?: string;
  name: string;
  args?: Record<string, JsonValue>;
}

export interface AppAgentActionFrame extends ActionFrameBase {
  data_type: "app.agent";
  appId: string;
  sessionId?: string;
  intent?: string;
  focus?: JsonValue;
  env?: Record<string, JsonValue>;
}

export interface ChatSendActionFrame extends ActionFrameBase {
  data_type: "chat.send";
  sessionId: string;
  intent?: string;
  username?: string;
}

export type ActionFrame =
  | AppInitActionFrame
  | AppCallActionFrame
  | AppAgentActionFrame
  | ChatSendActionFrame;

export interface EventData {
  type: string;
  requestId: string;
  seq?: number;
  ts?: number;
  appId?: string;
  appSession?: string;
  payload?: Record<string, JsonValue>;
}

export interface AppEventFrame {
  data_type: "app.event";
  data: EventData;
}

export interface ChatEventFrame {
  data_type: "chat.event";
  data: EventData;
}

export interface AppResourceApp {
  id: string;
  name: string;
  version: string;
  [key: string]: JsonValue;
}

export interface AppResourceDescriptor {
  uri: string;
  mimeType: string;
  [key: string]: JsonValue;
}

export interface AppResourceData {
  requestId: string;
  appId: string;
  appSession: string;
  seq?: number;
  app: AppResourceApp;
  resource: AppResourceDescriptor;
  [key: string]: JsonValue | undefined;
}

export interface AppResourceFrame {
  data_type: "app.resource";
  data: AppResourceData;
}

export type DownFrame = AppEventFrame | ChatEventFrame | AppResourceFrame;

export interface DebugPayload {
  data_type?: string;
  type?: string;
  data?: {
    type?: string;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface DebugFrame {
  data_type: "debug";
  dir: "up" | "down";
  ts: number;
  frame: DebugPayload;
}

export interface FileNode {
  name: string;
  path: string;
  type: "dir" | "file";
  kind?: "text" | "image" | "binary";
  size?: number;
  children?: FileNode[];
}

export interface FileTreeResponse {
  root: string;
  children: FileNode[];
}
