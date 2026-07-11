"""小程序框架 Demo 后端入口。"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import config
from .routers import apps_router, asr_router, config_router, files_router
from .ws_handler import handle_ws

app = FastAPI(title="MiniApp Framework Demo")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(apps_router.router)
app.include_router(files_router.router)
app.include_router(config_router.router)
app.include_router(asr_router.router)


@app.on_event("startup")
def _startup() -> None:
    config.ensure_directories()
    config.seed_bundled_apps()


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/sdk/{filename}")
def serve_sdk(filename: str):
    target = (config.SDK_DIR / filename).resolve()
    if config.SDK_DIR.resolve() not in target.parents or not target.is_file():
        raise HTTPException(404, "sdk file not found")
    return FileResponse(str(target), media_type="application/javascript")


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await handle_ws(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8790)
