"""技能文件管理:树 / 读 / 写 / 上传 / 移动 / 删除 / 图片预览。

所有路径都限定在小程序根目录内(防目录穿越)。
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import app_registry

router = APIRouter(prefix="/api/apps", tags=["files"])

_TEXT_EXT = {".md", ".txt", ".py", ".json", ".yaml", ".yml", ".html", ".css", ".js", ".ts", ".csv"}
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}


def _app_root(app_id: str) -> Path:
    manifest = app_registry.get_app(app_id)
    if manifest is None:
        raise HTTPException(404, "app not found")
    return manifest.root.resolve()


def _safe(root: Path, rel: str) -> Path:
    target = (root / rel).resolve()
    if root != target and root not in target.parents:
        raise HTTPException(400, "path escapes app root")
    return target


def _classify(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in _IMAGE_EXT:
        return "image"
    if ext in _TEXT_EXT:
        return "text"
    return "binary"


def _build_tree(root: Path, current: Path) -> List[Dict[str, Any]]:
    entries = []
    for child in sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        rel = str(child.relative_to(root))
        if child.is_dir():
            entries.append({
                "name": child.name,
                "path": rel,
                "type": "dir",
                "children": _build_tree(root, child),
            })
        else:
            entries.append({
                "name": child.name,
                "path": rel,
                "type": "file",
                "kind": _classify(child),
                "size": child.stat().st_size,
            })
    return entries


@router.get("/{app_id}/files")
def get_tree(app_id: str):
    root = _app_root(app_id)
    return {"root": app_id, "children": _build_tree(root, root)}


@router.get("/{app_id}/file")
def read_file(app_id: str, path: str):
    root = _app_root(app_id)
    target = _safe(root, path)
    if not target.is_file():
        raise HTTPException(404, "file not found")
    kind = _classify(target)
    if kind != "text":
        raise HTTPException(400, "not a text file")
    return {"path": path, "kind": kind, "content": target.read_text(encoding="utf-8", errors="replace")}


class WriteFileRequest(BaseModel):
    path: str
    content: str


@router.put("/{app_id}/file")
def write_file(app_id: str, req: WriteFileRequest):
    root = _app_root(app_id)
    target = _safe(root, req.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(req.content, encoding="utf-8")
    return {"ok": True, "path": req.path}


@router.post("/{app_id}/upload")
async def upload_file(app_id: str, dir: str = Form(""), file: UploadFile = File(...)):
    root = _app_root(app_id)
    target_dir = _safe(root, dir) if dir else root
    target_dir.mkdir(parents=True, exist_ok=True)
    target = _safe(root, str(Path(dir) / file.filename)) if dir else _safe(root, file.filename)
    with open(target, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"ok": True, "path": str(target.relative_to(root))}


class MoveRequest(BaseModel):
    src: str
    dst: str


@router.post("/{app_id}/move")
def move_file(app_id: str, req: MoveRequest):
    root = _app_root(app_id)
    src = _safe(root, req.src)
    dst = _safe(root, req.dst)
    if not src.exists():
        raise HTTPException(404, "src not found")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return {"ok": True, "src": req.src, "dst": req.dst}


@router.delete("/{app_id}/file")
def delete_file(app_id: str, path: str):
    root = _app_root(app_id)
    target = _safe(root, path)
    if not target.exists():
        raise HTTPException(404, "not found")
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return {"ok": True, "path": path}


@router.get("/{app_id}/raw")
def raw_file(app_id: str, path: str):
    root = _app_root(app_id)
    target = _safe(root, path)
    if not target.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(str(target))
