"""小程序列表 / 新建 / manifest / UI 资源服务。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import app_registry, stores

router = APIRouter(prefix="/api/apps", tags=["apps"])


class CreateAppRequest(BaseModel):
    name: str
    description: str = ""


@router.get("")
def list_apps():
    return [
        {
            "id": m.id,
            "name": m.name,
            "version": m.version,
            "description": m.description,
            "entry_ui": m.entry_ui,
        }
        for m in app_registry.list_apps()
    ]


@router.post("")
def create_app(req: CreateAppRequest):
    manifest = app_registry.create_app(req.name, req.description)
    return manifest.to_dict()


@router.get("/{app_id}/manifest")
def get_manifest(app_id: str):
    manifest = app_registry.get_app(app_id)
    if manifest is None:
        raise HTTPException(404, "app not found")
    return manifest.to_dict()


@router.get("/{app_id}/history")
def get_history(app_id: str):
    manifest = app_registry.get_app(app_id)
    if manifest is None:
        raise HTTPException(404, "app not found")
    session_id = stores.session_id_for("local", app_id)
    return stores.load_history(session_id)


@router.post("/{app_id}/reset-session")
def reset_session(app_id: str):
    manifest = app_registry.get_app(app_id)
    if manifest is None:
        raise HTTPException(404, "app not found")
    stores.reset_session("local", manifest)
    return {"status": "ok"}


@router.get("/{app_id}/ui/{asset_path:path}")
def serve_ui(app_id: str, asset_path: str):
    manifest = app_registry.get_app(app_id)
    if manifest is None:
        raise HTTPException(404, "app not found")
    ui_root = (manifest.root / "assets" / "ui").resolve()
    target = (ui_root / asset_path).resolve()
    if not str(target).startswith(str(ui_root)) or not target.is_file():
        raise HTTPException(404, "asset not found")
    return FileResponse(str(target))
