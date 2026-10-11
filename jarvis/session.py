"""Thread-safe wake/sleep generation gate, independent of APIs and microphones."""
from enum import Enum
import re
import threading
import time

class State(str, Enum):
    SLEEPING = "sleeping"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"

WAKE = {"wake up jarvis", "hey jarvis wake up", "jarvis wake up", "jarvis activate", "jarvis online", "hey jarvis"}
SLEEP = {"jarvis go to sleep", "jarvis sleep", "jarvis standby", "jarvis go offline", "go to sleep jarvis"}

def control_phrase(text):
    normalized = " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())
    if normalized in WAKE:
        return "wake"
    if normalized in SLEEP:
        return "sleep"
    return None

class Session:
    def __init__(self, hard_muted=False):
        self.lock = threading.RLock()
        self.generation = 0
        self.state = State.SLEEPING
        self.hard_muted = hard_muted
        self.last_control = 0.0

    def wake(self, from_voice=False):
        with self.lock:
            if from_voice and self.hard_muted:
                return False
            if self.state != State.SLEEPING:
                return False
            self.generation += 1
            self.state = State.LISTENING
            self.last_control = time.monotonic()
            return True

    def sleep(self):
        with self.lock:
            self.generation += 1
            self.state = State.SLEEPING
            self.last_control = time.monotonic()

    def valid(self, token):
        with self.lock:
            return self.state != State.SLEEPING and token == self.generation

    def invalidate(self):
        with self.lock:
            self.generation += 1
            if self.state != State.SLEEPING:
                self.state = State.LISTENING

    def require(self, token):
        if not self.valid(token):
            raise PermissionError("Session is sleeping or this action belongs to an expired conversation task.")

    def start_action(self, token):
        # Atomic dispatch point. A Windows action already started cannot be rolled back.
        with self.lock:
            self.require(token)

    def transition(self, token, state):
        with self.lock:
            if self.valid(token):
                self.state = State(state)

    def mute(self, value):
        with self.lock:
            self.hard_muted = value
