import threading
import time
import pytest
from jarvis.audio import Microphone
from jarvis.config import Settings

def test_hard_stop_aborts_closes_real_capture_owner(monkeypatch):
    opened = threading.Event()
    class Stream:
        active = True
        aborted = False
        closed = False
        def start(self):
            opened.set()
        def abort(self):
            self.aborted = True
            self.active = False
        def close(self):
            self.closed = True
    stream = Stream()
    monkeypatch.setattr("jarvis.audio.sd.query_devices", lambda *args: {"default_samplerate": 16000, "max_input_channels": 1})
    monkeypatch.setattr("jarvis.audio.sd.InputStream", lambda **kwargs: stream)
    mic = Microphone()
    results = []
    worker = threading.Thread(target=lambda: results.append(mic.capture(None, lambda level: None)))
    worker.start()
    assert opened.wait(2)
    mic.stop()
    worker.join(2)
    assert stream.aborted and stream.closed and not worker.is_alive()
    assert results == [b""] and mic.closed.is_set() and mic._stream is None

def test_stream_start_failure_releases_handle(monkeypatch):
    import sounddevice as sd
    class Stream:
        closed = False
        def start(self):
            raise sd.PortAudioError("test disconnected device")
        def close(self):
            self.closed = True
    stream = Stream()
    monkeypatch.setattr("jarvis.audio.sd.query_devices", lambda *args: {"default_samplerate": 16000, "max_input_channels": 1})
    monkeypatch.setattr("jarvis.audio.sd.InputStream", lambda **kwargs: stream)
    mic = Microphone()
    with pytest.raises(RuntimeError, match="Microphone unavailable"):
        mic.capture(None, lambda level: None)
    assert stream.closed and mic.closed.is_set() and mic._stream is None

def test_permissions_cannot_be_truthy_corrupted_strings():
    with pytest.raises(ValueError, match="booleans"):
        Settings(mic_enabled="false", wake_word=True).validate()

def test_missing_model_does_not_open_microphone(qapp, monkeypatch):
    from jarvis.listener import LocalListener
    from jarvis.session import Session
    listener = LocalListener(Settings(vosk_model="/nonexistent-model"), Session())
    listener.microphone.capture = lambda *a, **kw: pytest.fail("device opened without model")
    listener.start()
    listener.thread.join(3)
    assert not listener.thread.is_alive()
    listener.stop()
