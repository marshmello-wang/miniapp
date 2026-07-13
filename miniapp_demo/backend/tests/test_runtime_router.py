import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from miniapp_demo.backend import main
from miniapp_demo.backend.routers import runtime_router
from miniapp_demo.backend.runtime_service import DuplicateRequestError


class FakeRuntimeService:
    def __init__(self):
        self.frames = [
            {
                "data_type": "app.event",
                "data": {
                    "type": "done",
                    "requestId": "request-1",
                    "appId": "fortune",
                    "payload": {"status": "success"},
                },
            }
        ]
        self.last_frame = None
        self.cancelled = []
        self.duplicate = False

    def stream(self, frame):
        self.last_frame = frame
        if self.duplicate:
            raise DuplicateRequestError(frame["requestId"])

        async def generate():
            for item in self.frames:
                yield item

        return generate()

    async def cancel(self, request_id):
        self.cancelled.append(request_id)
        return "cancelled" if request_id == "active" else "not_found"


class BlockingEventStream:
    def __init__(self):
        self.closed = False
        self.gate = asyncio.Event()

    def __aiter__(self):
        return self

    async def __anext__(self):
        await self.gate.wait()
        raise StopAsyncIteration

    async def aclose(self):
        self.closed = True


class BlockingRuntimeService:
    def __init__(self):
        self.events = BlockingEventStream()

    def stream(self, frame):
        return self.events


class RuntimeRouterTest(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(runtime_router.router)
        self.client = TestClient(app)
        self.service = FakeRuntimeService()
        self.patcher = patch.object(
            runtime_router, "runtime_service", self.service
        )
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_action_returns_sse_frames_and_streaming_headers(self):
        response = self.client.post(
            "/api/runtime/actions",
            json={
                "data_type": "app.call",
                "appId": "fortune",
                "name": "draw",
                "requestId": "request-1",
            },
        )

        expected = f"data: {json.dumps(self.service.frames[0], ensure_ascii=False)}\n\n"
        self.assertEqual(200, response.status_code)
        self.assertEqual(expected, response.text)
        self.assertTrue(
            response.headers["content-type"].startswith("text/event-stream")
        )
        self.assertEqual("no-cache", response.headers["cache-control"])
        self.assertEqual("no", response.headers["x-accel-buffering"])
        self.assertEqual("app.call", self.service.last_frame["data_type"])

    def test_rejects_unknown_type_and_missing_request_id(self):
        unknown = self.client.post(
            "/api/runtime/actions",
            json={"data_type": "other", "requestId": "request-1"},
        )
        missing = self.client.post(
            "/api/runtime/actions",
            json={"data_type": "chat.send", "sessionId": "session-1"},
        )

        self.assertEqual(400, unknown.status_code)
        self.assertEqual(422, missing.status_code)

    def test_duplicate_request_id_returns_conflict(self):
        self.service.duplicate = True

        response = self.client.post(
            "/api/runtime/actions",
            json={
                "data_type": "app.agent",
                "appId": "fortune",
                "intent": "hello",
                "requestId": "request-1",
            },
        )

        self.assertEqual(409, response.status_code)

    def test_cancel_returns_explicit_json_status(self):
        cancelled = self.client.post("/api/runtime/actions/active/cancel")
        missing = self.client.post("/api/runtime/actions/missing/cancel")

        self.assertEqual({"requestId": "active", "status": "cancelled"}, cancelled.json())
        self.assertEqual({"requestId": "missing", "status": "not_found"}, missing.json())
        self.assertEqual(["active", "missing"], self.service.cancelled)

    def test_main_registers_runtime_routes(self):
        self.assertEqual(
            "/api/runtime/actions",
            str(main.app.url_path_for("create_action")),
        )
        self.assertEqual(
            "/api/runtime/actions/request-1/cancel",
            str(main.app.url_path_for("cancel_action", request_id="request-1")),
        )


class RuntimeRouterDisconnectTest(unittest.IsolatedAsyncioTestCase):
    async def test_closing_sse_generator_closes_runtime_stream(self):
        service = BlockingRuntimeService()
        with patch.object(runtime_router, "runtime_service", service):
            response = await runtime_router.create_action(
                {
                    "data_type": "app.init",
                    "appId": "fortune",
                    "requestId": "disconnect-1",
                }
            )
            pending = asyncio.create_task(anext(response.body_iterator))
            await asyncio.sleep(0)
            pending.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await pending
            await response.body_iterator.aclose()

        self.assertTrue(service.events.closed)

    async def test_main_shutdown_closes_global_runtime_service(self):
        shutdown = AsyncMock()
        with patch.object(runtime_router.runtime_service, "shutdown", shutdown):
            await main._shutdown()

        shutdown.assert_awaited_once_with()


if __name__ == "__main__":
    unittest.main()
