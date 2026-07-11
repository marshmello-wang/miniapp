import { api } from "../api/client";

export function ImagePreview({ appId, path }: { appId: string; path: string }) {
  return (
    <div className="editor-main">
      <div className="editor-toolbar">
        <strong>{path}</strong>
        <span className="muted">图片预览</span>
      </div>
      <div className="img-preview">
        <img src={api.rawUrl(appId, path)} alt={path} />
      </div>
    </div>
  );
}
