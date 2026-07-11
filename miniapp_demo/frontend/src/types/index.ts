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

export interface DownFrame {
  data_type: string;
  data?: any;
}

export interface DebugFrame {
  data_type: "debug";
  dir: "up" | "down";
  ts: number;
  frame: any;
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
