"""WebSocket 处理:客户端运行时(Host)<-> 引擎。

上行帧(Host -> 引擎):
- app.init   {appId, [sessionId]}
- app.call   {appId, name, args, requestId}      # direct_action
- app.agent  {appId, intent, focus, env, requestId, [sessionId]}  # agent_action
- chat.send  {sessionId, intent, username, requestId}  # chat action
- cancel     {requestId}

下行帧(引擎 -> Host):
- app.resource / app.event / chat.event
- debug      {dir: "up"|"down", frame}           # 每条上/下行帧镜像给 Debug 面板
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict

from fastapi import WebSocket, WebSocketDisconnect

from .engine import MiniAppEngine
from .chat_engine import ChatEngine


class WSConnection:
    def __init__(self, websocket: WebSocket, user: str = "local"):
        self.ws = websocket
        self.engine = MiniAppEngine(user=user)
        self.chat_engine = ChatEngine()
        self.tasks: Dict[str, asyncio.Task] = {}
        self._send_lock = asyncio.Lock()

    async def _raw_send(self, frame: Dict[str, Any]) -> None:
        async with self._send_lock:
            await self.ws.send_json(frame)

    async def _debug(self, direction: str, frame: Dict[str, Any]) -> None:
        await self._raw_send({
            "data_type": "debug",
            "dir": direction,
            "ts": time.time(),
            "frame": frame,
        })

    async def emit(self, frame: Dict[str, Any]) -> None:
        """下行:发帧 + 镜像 debug。"""
        await self._raw_send(frame)
        await self._debug("down", frame)

    async def run(self) -> None:
        await self.ws.accept()
        try:
            while True:
                msg = await self.ws.receive_json()
                await self._debug("up", msg)
                await self._dispatch(msg)
        except WebSocketDisconnect:
            pass
        finally:
            for task in self.tasks.values():
                task.cancel()

    async def _dispatch(self, msg: Dict[str, Any]) -> None:
        mtype = msg.get("data_type") or msg.get("type")
        if mtype == "app.init":
            await self._handle_init(msg)
        elif mtype == "app.call":
            self._spawn(msg.get("requestId", ""), self._run_direct(msg))
        elif mtype == "app.agent":
            self._spawn(msg.get("requestId", ""), self._run_agent(msg))
        elif mtype == "chat.send":
            self._spawn(msg.get("requestId", ""), self._run_chat(msg))
        elif mtype == "cancel":
            self._handle_cancel(msg)

    async def _handle_init(self, msg: Dict[str, Any]) -> None:
        app_id = msg.get("appId", "")
        session_id = msg.get("sessionId")
        info = self.engine.enter_app(app_id, session_id_override=session_id)
        if info is None:
            await self.emit({
                "data_type": "app.event",
                "data": {"type": "done", "payload": {"status": "error", "error": "app not found"}},
            })
            return
        await self.emit(info["resource"])

    async def _run_direct(self, msg: Dict[str, Any]) -> None:
        app_id = msg.get("appId", "")
        name = msg.get("name", "")
        args = msg.get("args", {}) or {}
        request_id = msg.get("requestId", "")
        session_id = msg.get("sessionId")
        async for frame in self.engine.direct_action(
            app_id, name, args, request_id,
            session_id_override=session_id,
        ):
            await self.emit(frame)

    async def _run_agent(self, msg: Dict[str, Any]) -> None:
        app_id = msg.get("appId", "")
        intent = msg.get("intent", "") or ""
        focus = msg.get("focus")
        env = msg.get("env")
        request_id = msg.get("requestId", "")
        session_id = msg.get("sessionId")
        async for frame in self.engine.agent_action(
            app_id, intent, focus, env, request_id,
            session_id_override=session_id,
        ):
            await self.emit(frame)

    async def _run_chat(self, msg: Dict[str, Any]) -> None:
        session_id = msg.get("sessionId", "")
        intent = msg.get("intent", "") or ""
        request_id = msg.get("requestId", "")
        async for frame in self.chat_engine.chat_action(session_id, intent, request_id):
            await self.emit(frame)

    def _spawn(self, request_id: str, coro) -> None:
        task = asyncio.create_task(self._guard(request_id, coro))
        if request_id:
            self.tasks[request_id] = task

    async def _guard(self, request_id: str, coro) -> None:
        try:
            await coro
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            await self.emit({
                "data_type": "app.event",
                "data": {"type": "done", "requestId": request_id,
                         "payload": {"status": "error", "error": str(exc)}},
            })
        finally:
            self.tasks.pop(request_id, None)

    def _handle_cancel(self, msg: Dict[str, Any]) -> None:
        request_id = msg.get("requestId", "")
        task = self.tasks.get(request_id)
        if task:
            task.cancel()


async def handle_ws(websocket: WebSocket) -> None:
    conn = WSConnection(websocket)
    await conn.run()
