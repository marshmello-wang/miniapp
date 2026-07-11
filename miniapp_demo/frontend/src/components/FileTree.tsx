import { useState } from "react";
import { api } from "../api/client";
import type { FileNode } from "../types";

interface Props {
  appId: string;
  nodes: FileNode[];
  selectedPath: string | null;
  onSelect: (node: FileNode) => void;
  onChanged: () => void;
}

const NODE_MIME = "application/x-miniapp-node";

export function FileTree({ appId, nodes, selectedPath, onSelect, onChanged }: Props) {
  return (
    <div className="tree">
      <RootDrop appId={appId} onChanged={onChanged}>
        {nodes.map((n) => (
          <TreeNode
            key={n.path}
            appId={appId}
            node={n}
            depth={0}
            selectedPath={selectedPath}
            onSelect={onSelect}
            onChanged={onChanged}
          />
        ))}
      </RootDrop>
    </div>
  );
}

function RootDrop({
  appId,
  onChanged,
  children,
}: {
  appId: string;
  onChanged: () => void;
  children: React.ReactNode;
}) {
  const [over, setOver] = useState(false);
  return (
    <div
      style={{ minHeight: "100%", background: over ? "#ecfdf5" : undefined }}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={async (e) => {
        e.preventDefault();
        setOver(false);
        await handleDrop(appId, "", e, onChanged);
      }}
    >
      {children}
    </div>
  );
}

async function handleDrop(
  appId: string,
  destDir: string,
  e: React.DragEvent,
  onChanged: () => void
) {
  const files = e.dataTransfer.files;
  if (files && files.length > 0) {
    for (const file of Array.from(files)) {
      await api.uploadFile(appId, destDir, file);
    }
    onChanged();
    return;
  }
  const src = e.dataTransfer.getData(NODE_MIME);
  if (src) {
    const name = src.split("/").pop()!;
    const dst = destDir ? `${destDir}/${name}` : name;
    if (dst !== src) {
      await api.moveFile(appId, src, dst);
      onChanged();
    }
  }
}

function TreeNode({
  appId,
  node,
  depth,
  selectedPath,
  onSelect,
  onChanged,
}: {
  appId: string;
  node: FileNode;
  depth: number;
  selectedPath: string | null;
  onSelect: (n: FileNode) => void;
  onChanged: () => void;
}) {
  const [expanded, setExpanded] = useState(true);
  const [over, setOver] = useState(false);
  const isDir = node.type === "dir";
  const pad = 8 + depth * 14;

  if (isDir) {
    return (
      <div>
        <div
          className={`tree-node ${over ? "dragover" : ""}`}
          style={{ paddingLeft: pad }}
          onClick={() => setExpanded((x) => !x)}
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={async (e) => {
            e.preventDefault();
            e.stopPropagation();
            setOver(false);
            await handleDrop(appId, node.path, e, onChanged);
          }}
        >
          {expanded ? "▾" : "▸"} 📁 {node.name}
        </div>
        {expanded &&
          node.children?.map((c) => (
            <TreeNode
              key={c.path}
              appId={appId}
              node={c}
              depth={depth + 1}
              selectedPath={selectedPath}
              onSelect={onSelect}
              onChanged={onChanged}
            />
          ))}
      </div>
    );
  }

  const icon = node.kind === "image" ? "🖼️" : node.kind === "text" ? "📄" : "📦";
  return (
    <div
      className={`tree-node ${selectedPath === node.path ? "selected" : ""}`}
      style={{ paddingLeft: pad }}
      draggable
      onDragStart={(e) => e.dataTransfer.setData(NODE_MIME, node.path)}
      onClick={() => onSelect(node)}
    >
      {icon} {node.name}
    </div>
  );
}
