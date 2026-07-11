"""LLM / agent 配置读写。"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter
from pydantic import BaseModel

from .. import config

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
def get_config():
    return config.load_config()


class UpdateConfigRequest(BaseModel):
    llm: Dict[str, Any] | None = None
    agent: Dict[str, Any] | None = None
    asr: Dict[str, Any] | None = None


@router.put("")
def update_config(req: UpdateConfigRequest):
    patch: Dict[str, Any] = {}
    if req.llm is not None:
        patch["llm"] = req.llm
    if req.agent is not None:
        patch["agent"] = req.agent
    if req.asr is not None:
        patch["asr"] = req.asr
    return config.update_config(patch)
