import asyncio
import unittest

from miniapp_demo.backend.runtime_service import (
    DuplicateRequestError,
    RuntimeService,
)


def app_event(request_id, event_type="done", status="success"):
    return {
        "data_type": "app.event",
        "data": {
            "type": event_type,
            "requestId": request_id,
            "payload": {"status": status},
        },
    }


def chat_event(request_id, event_type="done", status="success"):
    return {
        "data_type": "chat.event",
        "data": {
            "type": event_type,
            "requestId": request_id,
            "payload": {"status": status},
        },
    }


async def collect(stream):
    return [frame async for frame in stream]


class FakeEngine:
    def __init__(self):
        self.direct_gate = None
        self.done_exit_gate = None
        self.fail_direct = False
        self.flood_count = 0

    def enter_app(self, app_id, session_id_override=None):
        if app_id == "missing":
            return None
        return {
            "resource": {
                "data_type": "app.resource",
                "data": {
                    "appSession": session_id_override or "session-1",
                    "app": {"id": app_id},
                    "resource": {"uri": "/ui"},
                },
            }
        }

    async def direct_action(
        self, app_id, name, args, request_id, session_id_override=None
    ):
        if self.fail_direct:
            raise RuntimeError("direct exploded")
        if self.direct_gate is not None:
            await self.direct_gate.wait()
        for index in range(self.flood_count):
            yield app_event(request_id, f"event-{index}")
        try:
            yield app_event(request_id, "ui_update")
            yield app_event(request_id)
        finally:
            if self.done_exit_gate is not None:
                await self.done_exit_gate.wait()

    async def agent_action(
        self, app_id, intent, focus, env, request_id, session_id_override=None
    ):
        yield app_event(request_id, "text")
        yield app_event(request_id)


class FakeChatEngine:
    def __init__(self):
        self.gates = {}

    async def chat_action(self, session_id, intent, request_id):
        gate = self.gates.get(request_id)
        if gate is not None:
            await gate.wait()
        yield chat_event(request_id, "text")
        yield chat_event(request_id)


class RuntimeServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = FakeEngine()
        self.chat_engine = FakeChatEngine()
        self.service = RuntimeService(self.engine, self.chat_engine)

    async def test_init_emits_resource_then_done_with_app_and_request_ids(self):
        frames = await collect(
            self.service.stream(
                {
                    "data_type": "app.init",
                    "appId": "fortune",
                    "sessionId": "session-custom",
                    "requestId": "init-1",
                }
            )
        )

        self.assertEqual(["app.resource", "app.event"], [f["data_type"] for f in frames])
        self.assertEqual("done", frames[1]["data"]["type"])
        self.assertEqual("success", frames[1]["data"]["payload"]["status"])
        for frame in frames:
            self.assertEqual("fortune", frame["data"]["appId"])
            self.assertEqual("init-1", frame["data"]["requestId"])

    async def test_direct_and_agent_passthrough_add_app_identity(self):
        direct = await collect(
            self.service.stream(
                {
                    "data_type": "app.call",
                    "appId": "fortune",
                    "name": "draw",
                    "args": {"count": 1},
                    "requestId": "direct-1",
                }
            )
        )
        agent = await collect(
            self.service.stream(
                {
                    "data_type": "app.agent",
                    "appId": "fortune",
                    "intent": "interpret",
                    "focus": {"card": 1},
                    "env": {"theme": "dark"},
                    "requestId": "agent-1",
                }
            )
        )

        self.assertEqual(["ui_update", "done"], [f["data"]["type"] for f in direct])
        self.assertEqual(["text", "done"], [f["data"]["type"] for f in agent])
        for frame in direct + agent:
            self.assertEqual("fortune", frame["data"]["appId"])
            self.assertEqual(
                "direct-1" if frame in direct else "agent-1",
                frame["data"]["requestId"],
            )

    async def test_chat_passthrough_preserves_chat_event(self):
        frames = await collect(
            self.service.stream(
                {
                    "data_type": "chat.send",
                    "sessionId": "chat-session",
                    "intent": "hello",
                    "requestId": "chat-1",
                }
            )
        )

        self.assertEqual(["chat.event", "chat.event"], [f["data_type"] for f in frames])
        self.assertEqual(["text", "done"], [f["data"]["type"] for f in frames])

    async def test_engine_exception_becomes_matching_error_done(self):
        self.engine.fail_direct = True

        frames = await collect(
            self.service.stream(
                {
                    "data_type": "app.call",
                    "appId": "fortune",
                    "name": "draw",
                    "requestId": "error-1",
                }
            )
        )

        self.assertEqual(1, len(frames))
        self.assertEqual("app.event", frames[0]["data_type"])
        self.assertEqual("done", frames[0]["data"]["type"])
        self.assertEqual("error", frames[0]["data"]["payload"]["status"])
        self.assertIn("direct exploded", frames[0]["data"]["payload"]["error"])
        self.assertEqual("fortune", frames[0]["data"]["appId"])

    async def test_cancel_after_success_stream_cleanup_is_already_finished(self):
        await collect(
            self.service.stream(
                {
                    "data_type": "app.call",
                    "appId": "fortune",
                    "name": "draw",
                    "requestId": "completed-success",
                }
            )
        )

        self.assertEqual(
            "already_finished",
            await self.service.cancel("completed-success"),
        )

    async def test_cancel_after_error_stream_cleanup_is_already_finished(self):
        self.engine.fail_direct = True
        await collect(
            self.service.stream(
                {
                    "data_type": "app.call",
                    "appId": "fortune",
                    "name": "draw",
                    "requestId": "completed-error",
                }
            )
        )

        self.assertEqual(
            "already_finished",
            await self.service.cancel("completed-error"),
        )

    async def test_cancel_ends_original_stream_with_cancelled_done(self):
        self.engine.direct_gate = asyncio.Event()
        stream = self.service.stream(
            {
                "data_type": "app.call",
                "appId": "fortune",
                "name": "draw",
                "requestId": "cancel-1",
            }
        )
        pending_frame = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)

        status = await self.service.cancel("cancel-1")
        frame = await pending_frame

        self.assertEqual("cancelled", status)
        self.assertEqual("done", frame["data"]["type"])
        self.assertEqual("cancelled", frame["data"]["payload"]["status"])
        with self.assertRaises(StopAsyncIteration):
            await anext(stream)
        self.assertNotIn("cancel-1", self.service.active_request_ids)
        self.assertEqual("already_finished", await self.service.cancel("cancel-1"))

    async def test_cancel_unknown_request_remains_not_found(self):
        self.assertEqual("not_found", await self.service.cancel("never-seen"))

    async def test_completed_tombstones_evict_oldest_at_capacity(self):
        service = RuntimeService(
            self.engine,
            self.chat_engine,
            completed_limit=2,
        )
        for request_id in ("oldest", "newer", "newest"):
            await collect(
                service.stream(
                    {
                        "data_type": "app.call",
                        "appId": "fortune",
                        "name": "draw",
                        "requestId": request_id,
                    }
                )
            )

        self.assertEqual("not_found", await service.cancel("oldest"))
        self.assertEqual("already_finished", await service.cancel("newer"))
        self.assertEqual("already_finished", await service.cancel("newest"))
        self.assertEqual(2, len(service._completed))

    async def test_immediate_cancel_before_producer_starts_never_hangs(self):
        stream = self.service.stream(
            {
                "data_type": "app.call",
                "appId": "fortune",
                "name": "draw",
                "requestId": "immediate-cancel",
            }
        )

        status = await self.service.cancel("immediate-cancel")
        frames = await asyncio.wait_for(collect(stream), timeout=0.5)

        done = [frame for frame in frames if frame["data"]["type"] == "done"]
        self.assertEqual("cancelled", status)
        self.assertEqual(1, len(done))
        self.assertEqual("cancelled", done[0]["data"]["payload"]["status"])

    async def test_prestart_task_cancel_done_callback_finalizes_stream(self):
        stream = self.service.stream(
            {
                "data_type": "app.call",
                "appId": "fortune",
                "name": "draw",
                "requestId": "callback-cancel",
            }
        )
        request = self.service._requests["callback-cancel"]

        request.task.cancel()
        frames = await asyncio.wait_for(collect(stream), timeout=0.5)

        done = [frame for frame in frames if frame["data"]["type"] == "done"]
        self.assertEqual(1, len(done))
        self.assertEqual("cancelled", done[0]["data"]["payload"]["status"])
        self.assertTrue(request.queue.empty())

    async def test_done_queued_before_task_exit_cannot_be_overwritten_by_cancel(self):
        self.engine.done_exit_gate = asyncio.Event()
        stream = self.service.stream(
            {
                "data_type": "app.call",
                "appId": "fortune",
                "name": "draw",
                "requestId": "done-race",
            }
        )
        request = self.service._requests["done-race"]
        for _ in range(100):
            if request.queue.qsize() >= 2:
                break
            await asyncio.sleep(0)

        status = await self.service.cancel("done-race")
        self.engine.done_exit_gate.set()
        frames = await asyncio.wait_for(collect(stream), timeout=0.5)

        done = [frame for frame in frames if frame["data"]["type"] == "done"]
        self.assertEqual("already_finished", status)
        self.assertEqual(1, len(done))
        self.assertEqual("success", done[0]["data"]["payload"]["status"])
        self.assertTrue(request.queue.empty())

    async def test_cancel_after_producer_finishes_reports_already_finished(self):
        stream = self.service.stream(
            {
                "data_type": "app.call",
                "appId": "fortune",
                "name": "draw",
                "requestId": "finished-1",
            }
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        status = await self.service.cancel("finished-1")
        frames = await collect(stream)

        self.assertEqual("already_finished", status)
        self.assertEqual("success", frames[-1]["data"]["payload"]["status"])
        self.assertNotIn("finished-1", self.service.active_request_ids)

    async def test_duplicate_active_request_id_is_rejected(self):
        self.engine.direct_gate = asyncio.Event()
        first = self.service.stream(
            {
                "data_type": "app.call",
                "appId": "fortune",
                "name": "draw",
                "requestId": "duplicate-1",
            }
        )

        with self.assertRaises(DuplicateRequestError):
            self.service.stream(
                {
                    "data_type": "app.agent",
                    "appId": "fortune",
                    "intent": "hello",
                    "requestId": "duplicate-1",
                }
            )
        await first.aclose()

    async def test_concurrent_requests_do_not_mix_frames(self):
        gate_a = asyncio.Event()
        gate_b = asyncio.Event()
        self.chat_engine.gates = {"chat-a": gate_a, "chat-b": gate_b}
        stream_a = self.service.stream(
            {
                "data_type": "chat.send",
                "sessionId": "s",
                "intent": "a",
                "requestId": "chat-a",
            }
        )
        stream_b = self.service.stream(
            {
                "data_type": "chat.send",
                "sessionId": "s",
                "intent": "b",
                "requestId": "chat-b",
            }
        )
        result_a = asyncio.create_task(collect(stream_a))
        result_b = asyncio.create_task(collect(stream_b))

        gate_b.set()
        frames_b = await result_b
        self.assertFalse(result_a.done())
        gate_a.set()
        frames_a = await result_a

        self.assertEqual({"chat-a"}, {f["data"]["requestId"] for f in frames_a})
        self.assertEqual({"chat-b"}, {f["data"]["requestId"] for f in frames_b})

    async def test_closing_stream_cancels_producer_and_cleans_registry(self):
        self.engine.direct_gate = asyncio.Event()
        stream = self.service.stream(
            {
                "data_type": "app.call",
                "appId": "fortune",
                "name": "draw",
                "requestId": "close-1",
            }
        )
        waiter = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        waiter.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiter
        await stream.aclose()
        await asyncio.sleep(0)

        self.assertNotIn("close-1", self.service.active_request_ids)

    async def test_bounded_full_queue_does_not_deadlock_on_aclose(self):
        self.engine.flood_count = 1000
        stream = self.service.stream(
            {
                "data_type": "app.call",
                "appId": "fortune",
                "name": "draw",
                "requestId": "bounded-1",
            }
        )
        request = self.service._requests["bounded-1"]

        self.assertGreater(request.queue.maxsize, 0)
        for _ in range(100):
            if request.queue.full():
                break
            await asyncio.sleep(0)
        self.assertTrue(request.queue.full())

        await asyncio.wait_for(stream.aclose(), timeout=0.5)
        self.assertNotIn("bounded-1", self.service.active_request_ids)

    async def test_cancel_full_queue_emits_one_done_and_ends(self):
        self.engine.flood_count = 1000
        stream = self.service.stream(
            {
                "data_type": "app.call",
                "appId": "fortune",
                "name": "draw",
                "requestId": "bounded-cancel",
            }
        )
        request = self.service._requests["bounded-cancel"]
        for _ in range(100):
            if request.queue.full():
                break
            await asyncio.sleep(0)
        self.assertTrue(request.queue.full())

        status = await self.service.cancel("bounded-cancel")
        frames = await asyncio.wait_for(collect(stream), timeout=0.5)

        done = [frame for frame in frames if frame["data"]["type"] == "done"]
        self.assertEqual("cancelled", status)
        self.assertEqual(1, len(done))
        self.assertEqual("cancelled", done[0]["data"]["payload"]["status"])

    async def test_shutdown_cancels_all_producers_and_clears_registry(self):
        self.engine.direct_gate = asyncio.Event()
        stream_a = self.service.stream(
            {
                "data_type": "app.call",
                "appId": "fortune",
                "name": "draw",
                "requestId": "shutdown-a",
            }
        )
        stream_b = self.service.stream(
            {
                "data_type": "app.call",
                "appId": "fortune",
                "name": "draw",
                "requestId": "shutdown-b",
            }
        )
        await asyncio.sleep(0)

        await self.service.shutdown()
        frames_a = await collect(stream_a)
        frames_b = await collect(stream_b)

        self.assertEqual(frozenset(), self.service.active_request_ids)
        self.assertEqual("cancelled", frames_a[-1]["data"]["payload"]["status"])
        self.assertEqual("cancelled", frames_b[-1]["data"]["payload"]["status"])

    async def test_immediate_shutdown_before_producers_start_never_hangs(self):
        stream = self.service.stream(
            {
                "data_type": "app.call",
                "appId": "fortune",
                "name": "draw",
                "requestId": "immediate-shutdown",
            }
        )

        await self.service.shutdown()
        frames = await asyncio.wait_for(collect(stream), timeout=0.5)

        done = [frame for frame in frames if frame["data"]["type"] == "done"]
        self.assertEqual(1, len(done))
        self.assertEqual("cancelled", done[0]["data"]["payload"]["status"])
        self.assertEqual(frozenset(), self.service.active_request_ids)


if __name__ == "__main__":
    unittest.main()
