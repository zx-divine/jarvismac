"""One local microphone owner for standby/continuous listening. Never uses APIs."""
import threading
import time
from PySide6.QtCore import QObject, Signal
from .audio import Microphone
from .session import State

class LocalListener(QObject):
    heard = Signal(int, str, bytes)
    level = Signal(float)
    status = Signal(str)

    def __init__(self, settings, session):
        super().__init__()
        self.settings, self.session = settings, session
        self.microphone = Microphone()
        self.stopping = threading.Event()
        self.thread = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stopping.clear()
        self.thread = threading.Thread(target=self.run, name="jarvis-local-listener", daemon=True)
        self.thread.start()

    def run(self):
        try:
            # Validate/load the real model before opening the device; a missing model is visible.
            self.microphone.offline(b"", self.settings.vosk_model)
        except Exception:
            self.status.emit("Local wake detection unavailable. Select an extracted Vosk model in Settings; use manual Wake meanwhile.")
            return
        self.status.emit("Local wake detector ready. Speech stays on this computer in standby.")
        failed = False
        while not self.stopping.is_set():
            if self.session.hard_muted or self.session.state == State.SPEAKING or time.monotonic() < getattr(self.session, "capture_after", 0):
                # Half duplex prevents Windows/cloud TTS from triggering commands.
                self.stopping.wait(0.1)
                continue
            token = self.session.generation
            self.microphone.stop_event.clear()
            if self.stopping.is_set() or self.session.hard_muted:
                break
            try:
                pcm = self.microphone.capture(self.settings.mic_device, self.level.emit, max_seconds=8, threshold=self.settings.vad_threshold)
                if self.stopping.is_set() or self.session.hard_muted or self.session.state == State.SPEAKING or token != self.session.generation:
                    continue
                if failed:
                    self.status.emit("Microphone reconnected; local detection resumed.")
                    failed = False
                if pcm:
                    text = self.microphone.offline(pcm, self.settings.vosk_model)
                    self.heard.emit(token, text, pcm)
            except Exception:
                if not failed:
                    self.status.emit("Microphone disconnected or unavailable. Retrying locally; no cloud requests are made.")
                    failed = True
                self.stopping.wait(3)
        self.level.emit(0)

    def pause_capture(self):
        self.microphone.stop()

    def stop(self):
        self.stopping.set()
        self.microphone.stop()
        if self.thread:
            self.thread.join(timeout=2)
