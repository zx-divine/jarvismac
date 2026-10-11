import asyncio
import time
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from jarvis.ui import Window
from jarvis.storage import Store
from jarvis.security import SecretVault
from jarvis.session import State

def window(qapp, tmp_path):
    widget = Window(Store(tmp_path / "db.sqlite"), SecretVault(tmp_path), tmp_path)
    widget.mute_button.setChecked(True)
    widget.show()
    qapp.processEvents()
    return widget

def wait_until(qapp, predicate, timeout=3000):
    deadline = time.monotonic() + timeout / 1000
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(20)
    assert predicate()

def test_startup_sleep_ignores_normal_commands_and_hard_mute(qapp, tmp_path):
    w = window(qapp, tmp_path)
    try:
        assert w.session.state == State.SLEEPING
        w.input.setPlainText("Open Chrome")
        w.send()
        assert not w.busy and not w.history
        w.local_utterance(0, "open chrome", b"pcm")
        assert not w.busy
        w.local_utterance(0, "Wake up Jarvis", b"pcm")
        assert w.session.state == State.LISTENING
        token = w.session.generation
        w.local_utterance(token, "wake up jarvis", b"pcm")
        assert w.session.generation == token
        w.sleep()
        w.hard_mute_button.setChecked(True)
        w.local_utterance(w.session.generation, "wake up jarvis", b"pcm")
        assert w.session.state == State.SLEEPING and w.listener is None
        w.hard_mute_button.setChecked(False)
        w.wake()
        assert w.session.state == State.LISTENING
    finally:
        w.close()

def test_gui_responsive_cancellation_and_discard_late_events(qapp, tmp_path):
    w = window(qapp, tmp_path)
    try:
        w.wake()
        token = w.session.generation
        ticks = []
        timer = QTimer(w)
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start(20)
        async def delayed():
            await asyncio.sleep(10)
            return "late answer"
        assert w.begin("chat", delayed(), "completed")
        QTest.qWait(150)
        assert len(ticks) >= 3
        w.sleep()
        w.service_event(token, "text", "must not display")
        w.service_event(token, "completed", "must not persist")
        wait_until(qapp, lambda: not w.busy)
        assert "must not" not in w.chat.toPlainText()
        assert not w.history and w.session.state == State.SLEEPING
    finally:
        w.close()

def test_real_offline_quick_command(qapp, tmp_path):
    w = window(qapp, tmp_path)
    try:
        w.wake()
        w.quick("system_info", {})
        wait_until(qapp, lambda: not w.busy)
        assert "ram_percent" in w.chat.toPlainText()
        w.sleep()
        w.wake()
        w.quick("current_time", {})
        wait_until(qapp, lambda: not w.busy)
        assert "local_time" in w.chat.toPlainText()
    finally:
        w.close()

def test_normal_chat_resumes_after_wake(qapp, tmp_path):
    from jarvis.providers import Reply
    w = window(qapp, tmp_path)
    seen = []
    class FakeProvider:
        def __init__(self, *args):
            pass
        async def complete(self, messages, tools, on_text):
            seen.append(messages)
            await asyncio.sleep(0.05)
            on_text("Hello, ASH.")
            return Reply(text="Hello, ASH.")
    try:
        w.engine.provider_factory = FakeProvider
        w.settings.remember_history = True
        w.wake()
        w.input.setPlainText("Hello")
        w.send()
        wait_until(qapp, lambda: not w.busy)
        assert "Hello, ASH." in w.chat.toPlainText()
        assert len(w.store.messages(w.cid)) == 2
        w.sleep()
        w.wake()
        w.input.setPlainText("What did I just say?")
        w.send()
        wait_until(qapp, lambda: not w.busy)
        assert len(seen) == 2 and seen[1][1]["content"] == "Hello"
    finally:
        w.close()

def test_immediate_cancellation_does_not_stick_worker(qapp, tmp_path):
    w = window(qapp, tmp_path)
    try:
        w.wake()
        async def wait_forever():
            await asyncio.sleep(100)
            return "late"
        w.begin("chat", wait_forever(), "completed")
        w.sleep()
        wait_until(qapp, lambda: not w.busy)
        w.wake()
        w.quick("system_info", {})
        wait_until(qapp, lambda: not w.busy)
        assert "ram_percent" in w.chat.toPlainText()
    finally:
        w.close()

def test_hard_mute_discards_queued_voice_transcript(qapp, tmp_path):
    w = window(qapp, tmp_path)
    try:
        w.wake()
        token = w.session.generation
        w.transcript("Open Chrome")
        w.hard_mute_button.setChecked(True)
        w.service_event(token, "transcript", "Open Chrome")
        w.hard_mute_button.setChecked(False)
        w.service_event(token, "transcript", "Open Chrome")
        w.task_idle()
        QTest.qWait(150)
        assert not w.pending_send and not w.history and not w.busy
    finally:
        w.close()
