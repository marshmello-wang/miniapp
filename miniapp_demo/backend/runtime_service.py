"""统一 Action 运行时服务。

每个 requestId 对应一个短生命周期 producer 和独立队列，响应流结束或关闭时清理。
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, Literal, Optional

from . import protocol
from .chat_engine import ChatEngine
from .engine import MiniAppEngine

_QUEUE_CAPACITY = 32


class DuplicateRequestError(ValueError):
    """同一 requestId 已有活动流。"""


@dataclass
class _Request:
    queue: asyncio.Queue
    frame: Dict[str, Any]
    task: Optional[asyncio.Task] = None
    state: Literal["running", "finished", "cancelled"] = "running"
    terminal_status: Optional[Literal["success", "error", "cancelled"]] = None
    finalized: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class _RequestStream:
    def __init__(
        self,
        service: "RuntimeService",
        request_id: str,
        request: _Request,
    ):
        self._service = service
        self._request_id = request_id
        self._request = request
        self._closed = False

    def __aiter__(self) -> "_RequestStream":
        return self

    async def __anext__(self) -> Dict[str, Any]:
        if self._closed:
            raise StopAsyncIteration
        item = await self._request.queue.get()
        if item is self._service._sentinel:
            await self.aclose(cancel_producer=False)
            raise StopAsyncIteration
        return item

    async def aclose(self, cancel_producer: bool = True) -> None:
        if self._closed:
            return
        self._closed = True
        task = self._request.task
        if task is None:
            self._service._remove(self._request_id, self._request)
            return
        if cancel_producer and not task.done():
            status = await self._service._cancel_request(self._request)
            if status == "already_finished" and not task.done():
                task.cancel()
        elif not task.done() and self._request.finalized:
            task.cancel()
        if not task.done():
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._service._remove(self._request_id, self._request)


class RuntimeService:
    def __init__(
        self,
        engine: Optional[MiniAppEngine] = None,
        chat_engine: Optional[ChatEngine] = None,
        completed_limit: int = 256,
    ):
        self.engine = engine or MiniAppEngine(user="local")
        self.chat_engine = chat_engine or ChatEngine()
        self._requests: Dict[str, _Request] = {}
        self._completed: OrderedDict[str, str] = OrderedDict()
        self._completed_limit = max(1, completed_limit)
        self._sentinel = object()

    @property
    def active_request_ids(self):
        return frozenset(self._requests)

    def stream(self, frame: Dict[str, Any]) -> AsyncIterator[Dict[str, Any]]:
        """占用 requestId 并返回本次 Action 的独立异步事件流。"""
        request_id = frame.get("requestId", "")
        if not request_id:
            raise ValueError("requestId is required")
        if request_id in self._requests:
            raise DuplicateRequestError(request_id)

        self._completed.pop(request_id, None)
        queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_CAPACITY)
        request = _Request(queue=queue, frame=dict(frame))
        self._requests[request_id] = request
        request.task = asyncio.create_task(self._produce(frame, request))
        request.task.add_done_callback(
            lambda task: self._producer_done(request, task)
        )
        return _RequestStream(self, request_id, request)

    async def cancel(self, request_id: str) -> str:
        request = self._requests.get(request_id)
        if request is None:
            if request_id in self._completed:
                self._completed.move_to_end(request_id)
                return "already_finished"
            return "not_found"
        return await self._cancel_request(request)

    async def shutdown(self) -> None:
        """取消并等待所有活动 producer，随后清空 registry。"""
        requests = list(self._requests.values())
        tasks = []
        for request in requests:
            await self._cancel_request(request)
            if request.task is not None:
                tasks.append(request.task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for request_id, request in self._requests.items():
            self._remember_completed(request_id, request)
        self._requests.clear()

    async def _produce(
        self,
        frame: Dict[str, Any],
        request: _Request,
    ) -> None:
        try:
            async for event in self._dispatch(frame):
                normalized = self._normalize(event, frame)
                if self._is_done(normalized):
                    status = normalized["data"]["payload"].get("status", "success")
                    await self._finalize(
                        request,
                        status if status in ("success", "error", "cancelled") else "success",
                        terminal_frame=normalized,
                    )
                    return
                await request.queue.put(normalized)
        except asyncio.CancelledError:
            await self._finalize(request, "cancelled")
        except Exception as exc:  # noqa: BLE001
            await self._finalize(request, "error", error=str(exc))
        else:
            await self._finalize(request, "success")

    async def _cancel_request(self, request: _Request) -> str:
        async with request.lock:
            if request.terminal_status == "cancelled":
                return "cancelled"
            if request.terminal_status is not None:
                return "already_finished"
            request.terminal_status = "cancelled"
            request.state = "cancelled"
        task = request.task
        if task is not None and not task.done():
            task.cancel()
        await self._finalize(request, "cancelled")
        return "cancelled"

    async def _finalize(
        self,
        request: _Request,
        status: Literal["success", "error", "cancelled"],
        *,
        terminal_frame: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> bool:
        async with request.lock:
            if request.finalized:
                return False
            if (
                request.terminal_status is not None
                and request.terminal_status != status
            ):
                return False
            request.terminal_status = status
            request.state = "cancelled" if status == "cancelled" else "finished"
            request.finalized = True
            done = terminal_frame or self._done_frame(
                request.frame,
                status,
                error,
            )
            self._append_terminal(request.queue, done)
            return True

    def _producer_done(
        self,
        request: _Request,
        task: asyncio.Task,
    ) -> None:
        loop = task.get_loop()
        if loop.is_closed():
            return
        if task.cancelled():
            status = request.terminal_status or "cancelled"
            error = None
        else:
            exc = task.exception()
            status = "error" if exc is not None else (
                request.terminal_status or "success"
            )
            error = str(exc) if exc is not None else None
        loop.create_task(self._finalize(request, status, error=error))

    async def _dispatch(
        self,
        frame: Dict[str, Any],
    ) -> AsyncIterator[Dict[str, Any]]:
        data_type = frame.get("data_type")
        request_id = frame["requestId"]

        if data_type == "app.init":
            info = self.engine.enter_app(
                frame.get("appId", ""),
                session_id_override=frame.get("sessionId"),
            )
            if info is None:
                yield self._done_frame(frame, "error", "app not found")
                return
            yield info["resource"]
            yield self._done_frame(frame, "success")
            return

        if data_type == "app.call":
            source = self.engine.direct_action(
                frame.get("appId", ""),
                frame.get("name", ""),
                frame.get("args", {}) or {},
                request_id,
                session_id_override=frame.get("sessionId"),
            )
        elif data_type == "app.agent":
            source = self.engine.agent_action(
                frame.get("appId", ""),
                frame.get("intent", "") or "",
                frame.get("focus"),
                frame.get("env"),
                request_id,
                session_id_override=frame.get("sessionId"),
            )
        elif data_type == "chat.send":
            source = self.chat_engine.chat_action(
                frame.get("sessionId", ""),
                frame.get("intent", "") or "",
                request_id,
            )
        else:
            raise ValueError(f"unsupported data_type: {data_type}")

        async for event in source:
            yield event

    def _normalize(
        self,
        event: Dict[str, Any],
        request_frame: Dict[str, Any],
    ) -> Dict[str, Any]:
        normalized = dict(event)
        data = dict(event.get("data") or {})
        normalized["data"] = data
        data["requestId"] = request_frame["requestId"]
        if request_frame.get("data_type", "").startswith("app."):
            data["appId"] = request_frame.get("appId", "")
        return normalized

    def _done_frame(
        self,
        request_frame: Dict[str, Any],
        status: str,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {"status": status}
        if error is not None:
            payload["error"] = error
        request_id = request_frame.get("requestId", "")
        if request_frame.get("data_type") == "chat.send":
            return {
                "data_type": "chat.event",
                "data": {
                    "type": "done",
                    "requestId": request_id,
                    "payload": payload,
                },
            }
        return protocol.make_event_frame(
            "done",
            request_frame.get("sessionId", ""),
            request_id,
            0,
            payload,
            app_id=request_frame.get("appId", ""),
        )

    def _remove(self, request_id: str, request: _Request) -> None:
        if self._requests.get(request_id) is request:
            self._requests.pop(request_id, None)
        self._remember_completed(request_id, request)

    def _remember_completed(
        self,
        request_id: str,
        request: _Request,
    ) -> None:
        if not request.finalized or request.terminal_status is None:
            return
        self._completed[request_id] = request.terminal_status
        self._completed.move_to_end(request_id)
        while len(self._completed) > self._completed_limit:
            self._completed.popitem(last=False)

    @staticmethod
    def _is_done(frame: Dict[str, Any]) -> bool:
        return (
            frame.get("data_type") in ("app.event", "chat.event")
            and (frame.get("data") or {}).get("type") == "done"
        )

    def _append_terminal(
        self,
        queue: asyncio.Queue,
        done: Dict[str, Any],
    ) -> None:
        required = 2
        while queue.maxsize and queue.qsize() > queue.maxsize - required:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        queue.put_nowait(done)
        queue.put_nowait(self._sentinel)
