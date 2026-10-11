"""One asyncio service thread. Qt widgets are only touched on the UI thread."""
import asyncio
from concurrent.futures import Future
import threading
from PySide6.QtCore import QObject, Signal

class Service(QObject):
    event = Signal(int, str, object)
    text = Signal(str)
    completed = Signal(str)
    failed = Signal(str)
    usage = Signal(object)
    audit = Signal(str, bool)
    approval = Signal(int, object, object, object)
    transcript = Signal(str)
    level = Signal(float)
    speech_audio = Signal(bytes)
    idle = Signal()

    def __init__(self):
        super().__init__()
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, name="jarvis-services", daemon=True)
        self.thread.start()
        self.task = None
        self.active = threading.Event()
        self.cancel_requested = threading.Event()
        self.async_task = None
        self.validity = lambda generation: True
        self.pending_approvals = set()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def approve(self, tool, args, generation=0):
        answer = Future()
        self.pending_approvals.add(answer)
        self.approval.emit(generation, tool, args, answer)
        try:
            return await asyncio.wrap_future(answer)
        finally:
            self.pending_approvals.discard(answer)

    def submit(self, coroutine, callback_kind, generation=0):
        if self.active.is_set():
            coroutine.close()
            return False
        self.active.set()
        self.cancel_requested.clear()
        async def run():
            try:
                self.async_task = asyncio.current_task()
                if self.cancel_requested.is_set() or not self.validity(generation):
                    coroutine.close()
                    return
                result = await coroutine
                self.event.emit(generation, callback_kind, result)
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                from .security import scrub
                self.event.emit(generation, "failed", scrub(str(exc))[:1500])
            finally:
                self.async_task = None
                self.active.clear()
                self.event.emit(generation, "idle", None)
        self.task = asyncio.run_coroutine_threadsafe(run(), self.loop)
        return True

    def cancel(self):
        self.cancel_requested.set()
        def cancel_task():
            if self.async_task:
                self.async_task.cancel()
        self.loop.call_soon_threadsafe(cancel_task)
        for answer in list(self.pending_approvals):
            if not answer.done():
                answer.set_result(False)

    def close(self):
        self.cancel()
        async def shutdown():
            pending = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        try:
            asyncio.run_coroutine_threadsafe(shutdown(), self.loop).result(timeout=5)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(timeout=3)
