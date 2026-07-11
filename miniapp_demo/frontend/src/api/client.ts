import type { AppInfo, AppManifest, FileTreeResponse } from "../types";

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText} ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listApps: () => fetch("/api/apps").then((r) => j<AppInfo[]>(r)),

  createApp: (name: string, description: string) =>
    fetch("/api/apps", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description }),
    }).then((r) => j<AppManifest>(r)),

  manifest: (appId: string) =>
    fetch(`/api/apps/${appId}/manifest`).then((r) => j<AppManifest>(r)),

  fileTree: (appId: string) =>
    fetch(`/api/apps/${appId}/files`).then((r) => j<FileTreeResponse>(r)),

  readFile: (appId: string, path: string) =>
    fetch(`/api/apps/${appId}/file?path=${encodeURIComponent(path)}`).then((r) =>
      j<{ path: string; kind: string; content: string }>(r)
    ),

  writeFile: (appId: string, path: string, content: string) =>
    fetch(`/api/apps/${appId}/file`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, content }),
    }).then((r) => j<{ ok: boolean }>(r)),

  uploadFile: (appId: string, dir: string, file: File) => {
    const fd = new FormData();
    fd.append("dir", dir);
    fd.append("file", file);
    return fetch(`/api/apps/${appId}/upload`, { method: "POST", body: fd }).then(
      (r) => j<{ ok: boolean; path: string }>(r)
    );
  },

  moveFile: (appId: string, src: string, dst: string) =>
    fetch(`/api/apps/${appId}/move`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ src, dst }),
    }).then((r) => j<{ ok: boolean }>(r)),

  deleteFile: (appId: string, path: string) =>
    fetch(`/api/apps/${appId}/file?path=${encodeURIComponent(path)}`, {
      method: "DELETE",
    }).then((r) => j<{ ok: boolean }>(r)),

  rawUrl: (appId: string, path: string) =>
    `/api/apps/${appId}/raw?path=${encodeURIComponent(path)}`,

  getConfig: () => fetch("/api/config").then((r) => j<any>(r)),

  updateConfig: (patch: any) =>
    fetch("/api/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }).then((r) => j<any>(r)),
};
