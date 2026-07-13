"""小程序框架 Demo 后端入口。"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import config
from .routers import (
    apps_router,
    asr_router,
    chat_router,
    config_router,
    files_router,
    runtime_router,
)
app = FastAPI(title="MiniApp Framework Demo")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(apps_router.router)
app.include_router(chat_router.router)
app.include_router(files_router.router)
app.include_router(config_router.router)
app.include_router(asr_router.router)
app.include_router(runtime_router.router)


@app.on_event("startup")
def _startup() -> None:
    config.ensure_directories()
    config.load_config()
    config.seed_bundled_apps()


@app.on_event("shutdown")
async def _shutdown() -> None:
    await runtime_router.runtime_service.shutdown()


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/sdk/{filename}")
def serve_sdk(filename: str):
    target = (config.SDK_DIR / filename).resolve()
    if config.SDK_DIR.resolve() not in target.parents or not target.is_file():
        raise HTTPException(404, "sdk file not found")
    return FileResponse(str(target), media_type="application/javascript")


# ---------- SPA static file serving (production) ----------
_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if _FRONTEND_DIST.is_dir():
    @app.get("/{full_path:path}")
    async def spa_fallback(request: Request, full_path: str):
        file = _FRONTEND_DIST / full_path
        if full_path and file.is_file():
            return FileResponse(str(file))
        return FileResponse(str(_FRONTEND_DIST / "index.html"))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8790)
