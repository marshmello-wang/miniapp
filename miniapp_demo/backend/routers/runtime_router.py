"""统一 Action POST + SSE API。"""
from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import StreamingResponse

from ..runtime_service import DuplicateRequestError, RuntimeService


router = APIRouter(prefix="/api/runtime", tags=["runtime"])
runtime_service = RuntimeService()

_REQUIRED_FIELDS = {
    "app.init": ("requestId", "appId"),
    "app.call": ("requestId", "appId", "name"),
    "app.agent": ("requestId", "appId"),
    "chat.send": ("requestId", "sessionId"),
}


@router.post("/actions")
async def create_action(frame: Dict[str, Any] = Body(...)):
    data_type = frame.get("data_type")
    if data_type not in _REQUIRED_FIELDS:
        raise HTTPException(status_code=400, detail="unsupported data_type")
    missing = [field for field in _REQUIRED_FIELDS[data_type] if not frame.get(field)]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"missing required field(s): {', '.join(missing)}",
        )

    try:
        events = runtime_service.stream(frame)
    except DuplicateRequestError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"requestId already active: {exc}",
        ) from exc

    async def encode_sse():
        try:
            async for event in events:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            close = getattr(events, "aclose", None)
            if close is not None:
                await close()

    return StreamingResponse(
        encode_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/actions/{request_id}/cancel")
async def cancel_action(request_id: str):
    status = await runtime_service.cancel(request_id)
    return {"requestId": request_id, "status": status}
