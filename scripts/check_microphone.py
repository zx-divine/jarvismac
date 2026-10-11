"""Explicit one-second input-device check. Saves and uploads no microphone audio."""
import numpy as np
import sounddevice as sd

device = sd.query_devices(kind="input")
rate = int(device["default_samplerate"])
print("Checking default input:", device["name"])
audio = sd.rec(rate, samplerate=rate, channels=1, dtype="float32")
sd.wait()
assert audio.shape == (rate, 1)
print("Captured frames:", len(audio), "at", rate, "Hz")
print("Signal RMS:", round(float(np.sqrt(np.mean(audio ** 2))), 6))
print("Audio was not saved or uploaded. This checks capture, not ASH's wake-word accuracy.")
