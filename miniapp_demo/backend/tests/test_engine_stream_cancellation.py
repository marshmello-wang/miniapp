import asyncio
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from miniapp_demo.backend import chat_engine as chat_engine_module
from miniapp_demo.backend import engine as engine_module
from miniapp_demo.backend.chat_engine import ChatEngine
from miniapp_demo.backend.engine import MiniAppEngine


class BlockingWorkerIterator:
    def __init__(self):
        self.next_calls = 0
        self.second_started = threading.Event()
        self.release_second = threading.Event()
        self.closed = threading.Event()

    def __iter__(self):
        return self

    def __next__(self):
        self.next_calls += 1
        if self.next_calls == 1:
            return "first"
        if self.next_calls == 2:
            self.second_started.set()
            self.release_second.wait(timeout=2)
            return "second"
        raise StopIteration

    def close(self):
        self.closed.set()


class TrackingQueue:
    def __init__(self):
        self._queue = asyncio.Queue()
        self.delivered = []

    def put_nowait(self, item):
        self.delivered.append(item)
        self._queue.put_nowait(item)

    async def get(self):
        return await self._queue.get()


class EngineStreamCancellationTest(unittest.IsolatedAsyncioTestCase):
    async def test_agent_stream_aclose_stops_worker_and_drops_late_item(self):
        source = BlockingWorkerIterator()
        queue = TrackingQueue()
        miniapp_engine = MiniAppEngine()

        with (
            patch.object(engine_module.asyncio, "Queue", return_value=queue),
            patch.object(engine_module, "run_agent", return_value=source),
        ):
            stream = miniapp_engine._stream_agent(
                object(), Path("."), "session", "task", "message", []
            )
            self.assertEqual("first", await anext(stream))
            self.assertTrue(source.second_started.wait(timeout=1))

            await stream.aclose()
            source.release_second.set()
            self.assertTrue(await asyncio.to_thread(source.closed.wait, 1))
            await asyncio.sleep(0)

        self.assertEqual(2, source.next_calls)
        self.assertEqual(["first"], queue.delivered)

    async def test_chat_stream_aclose_stops_worker_and_drops_late_item(self):
        source = BlockingWorkerIterator()
        queue = TrackingQueue()
        chat_engine = ChatEngine()

        with (
            patch.object(chat_engine_module.asyncio, "Queue", return_value=queue),
            patch.object(chat_engine_module, "run_chat_agent", return_value=source),
            patch.object(
                chat_engine_module.stores,
                "business_store_dir",
                return_value=Path("."),
            ),
        ):
            stream = chat_engine._stream_chat(
                "session", "task", "message", []
            )
            self.assertEqual("first", await anext(stream))
            self.assertTrue(source.second_started.wait(timeout=1))

            await stream.aclose()
            source.release_second.set()
            self.assertTrue(await asyncio.to_thread(source.closed.wait, 1))
            await asyncio.sleep(0)

        self.assertEqual(2, source.next_calls)
        self.assertEqual(["first"], queue.delivered)


if __name__ == "__main__":
    unittest.main()
