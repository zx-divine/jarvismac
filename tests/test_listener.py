import threading
import time
from jarvis.listener import LocalListener
from jarvis.session import Session
from jarvis.config import Settings

def test_hard_muted_listener_never_opens_device(qapp):
    session = Session(hard_muted=True)
    listener = LocalListener(Settings(), session)
    calls = []
    listener.microphone.offline = lambda *args: ""
    listener.microphone.capture = lambda *args, **kw: calls.append(1)
    listener.start()
    time.sleep(0.15)
    listener.stop()
    assert not calls and not listener.thread.is_alive()

def test_microphone_disconnection_does_not_crash(qapp):
    listener = LocalListener(Settings(), Session())
    entered = threading.Event()
    listener.microphone.offline = lambda *args: ""
    def unplugged(*args, **kw):
        entered.set()
        raise RuntimeError("device disconnected")
    listener.microphone.capture = unplugged
    listener.start()
    assert entered.wait(2)
    listener.stop()
    assert not listener.thread.is_alive()
