"""Bounded in-memory microphone capture, energy VAD, optional offline Vosk."""
import asyncio
import io
import json
from pathlib import Path
import threading
import time
import wave
from collections import OrderedDict
import numpy as np
import sounddevice as sd
import httpx
from .providers import ProviderError

_models = OrderedDict()
_model_lock = threading.Lock()

class Microphone:
    def __init__(self):
        self.stop_event = threading.Event()
        self._model = None
        self._model_path = ""
        self._stream = None
        self._stream_lock = threading.Lock()
        self.closed = threading.Event()
        self.closed.set()

    def stop(self):
        self.stop_event.set()
        with self._stream_lock:
            if self._stream is not None:
                try:
                    self._stream.abort()
                except sd.PortAudioError:
                    pass
        self.closed.wait(1)

    def capture(self, device, on_level, max_seconds=20, threshold=0.012):
        if self.stop_event.is_set():
            return b""
        info = sd.query_devices(device, "input")
        rate = int(info["default_samplerate"])
        if rate < 8000 or rate > 192000 or info["max_input_channels"] < 1:
            raise RuntimeError("Selected device has no supported mono audio input. Choose an input device in Settings.")
        chunks = []
        state = {"speech": False, "last_voice": time.monotonic(), "samples": 0, "device_error": False, "overflows": 0}
        limit = rate * max_seconds
        def callback(indata, frames, timing, status):
            if status:
                state["overflows"] += 1
                if not status.input_overflow or state["overflows"] > 5:
                    state["device_error"] = True
                    raise sd.CallbackAbort
            if self.stop_event.is_set() or state["samples"] >= limit:
                raise sd.CallbackStop
            audio = indata[:, 0].copy()
            level = float(np.sqrt(np.mean(audio ** 2)))
            on_level(min(1.0, level * 10))
            state["samples"] += len(audio)
            chunks.append(audio)
            if level >= threshold:
                state["speech"] = True
                state["last_voice"] = time.monotonic()
            elif state["speech"] and time.monotonic() - state["last_voice"] > 1.2:
                raise sd.CallbackStop
        stream = None
        try:
            with self._stream_lock:
                if self.stop_event.is_set():
                    return b""
                self.closed.clear()
                stream = sd.InputStream(device=device, samplerate=rate, channels=1, dtype="float32", blocksize=max(1, rate // 20), callback=callback)
                self._stream = stream
                stream.start()
            try:
                deadline = time.monotonic() + max_seconds + 1
                while stream.active and not self.stop_event.is_set() and time.monotonic() < deadline:
                    self.stop_event.wait(0.05)
            finally:
                with self._stream_lock:
                    self._stream = None
                    stream.close()
        except sd.PortAudioError as exc:
            raise RuntimeError("Microphone unavailable. Check OS microphone permission, device selection, and reconnect the device.") from exc
        finally:
            with self._stream_lock:
                if self._stream is not None:
                    self._stream = None
                    if stream is not None:
                        stream.close()
            self.closed.set()
            on_level(0)
        if self.stop_event.is_set():
            return b""
        on_level(0)
        if state["device_error"]:
            raise RuntimeError("Microphone stream interrupted. Check device connection and input settings.")
        if not state["speech"] or not chunks:
            return b""
        audio = np.concatenate(chunks)
        if rate != 16000:
            audio = np.interp(np.arange(int(len(audio) * 16000 / rate)) * rate / 16000, np.arange(len(audio)), audio)
        return (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()

    def offline(self, pcm, model_path):
        try:
            from vosk import Model, KaldiRecognizer, SetLogLevel
        except ImportError as exc:
            raise RuntimeError("Offline recognition needs requirements-offline-voice.txt and a downloaded Vosk model folder.") from exc
        path = Path(model_path)
        if not path.is_dir() or not (path / "am").is_dir():
            raise RuntimeError("Choose an extracted Vosk model folder containing the am directory.")
        if self._model is None or self._model_path != str(path):
            # One cold load per path, even during rapid listener restarts.
            with _model_lock:
                SetLogLevel(-1)
                key = str(path.resolve())
                if key not in _models:
                    _models[key] = Model(key)
                self._model = _models[key]
                _models.move_to_end(key)
                while len(_models) > 2:
                    _models.popitem(last=False)
            self._model_path = str(path)
        recognizer = KaldiRecognizer(self._model, 16000)
        recognizer.AcceptWaveform(pcm)
        return json.loads(recognizer.FinalResult()).get("text", "").strip()

async def transcribe(settings, vault, microphone, on_level):
    if not settings.mic_enabled:
        raise PermissionError("Microphone access is disabled. Enable it in Settings first.")
    capture_task = asyncio.create_task(asyncio.to_thread(microphone.capture, settings.mic_device, on_level, 20, settings.vad_threshold))
    try:
        pcm = await asyncio.shield(capture_task)
    except asyncio.CancelledError:
        microphone.stop()
        await capture_task
        raise
    if not pcm:
        return ""
    if settings.recognition == "vosk":
        return await asyncio.to_thread(microphone.offline, pcm, settings.vosk_model)
    return await transcribe_pcm(settings, vault, pcm)

async def transcribe_pcm(settings, vault, pcm):
    if not pcm:
        return ""
    if settings.recognition == "gemini":
        from .gemini import transcribe_gemini
        return await transcribe_gemini(settings, vault, pcm)
    key = vault.get("audio", settings.audio_endpoint)
    if not key:
        raise ProviderError("Save a separate audio API key in Settings, or choose offline Vosk speech recognition.")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(pcm)
    data = {"model": settings.transcription_model}
    if settings.language in {"en", "hi"}:
        data["language"] = settings.language
    async with httpx.AsyncClient(timeout=45, trust_env=False, follow_redirects=False) as client:
        try:
            response = await client.post(settings.audio_endpoint + "/audio/transcriptions", headers={"Authorization": "Bearer " + key}, data=data, files={"file": ("speech.wav", buffer.getvalue(), "audio/wav")})
            if response.status_code != 200:
                raise ProviderError(f"Speech API returned HTTP {response.status_code}. Check audio key, model, endpoint and billing.")
            return response.json().get("text", "").strip()[:8000]
        except httpx.HTTPError as exc:
            raise ProviderError("Speech transcription failed. Check your internet connection.") from exc

async def synthesize(settings, vault, text):
    key = vault.get("audio", settings.audio_endpoint)
    if not key:
        raise ProviderError("Cloud speech needs an audio API key in Settings. Local Windows speech needs no API key.")
    body = {"model": settings.speech_model, "voice": settings.speech_voice, "input": text[:4000], "response_format": "wav", "speed": max(0.25, min(4.0, 1 + settings.voice_rate))}
    async with httpx.AsyncClient(timeout=60, trust_env=False, follow_redirects=False) as client:
        try:
            async with client.stream("POST", settings.audio_endpoint + "/audio/speech", headers={"Authorization": "Bearer " + key}, json=body) as response:
                if response.status_code != 200:
                    raise ProviderError(f"Speech synthesis API returned HTTP {response.status_code}.")
                audio = bytearray()
                async for chunk in response.aiter_bytes():
                    audio.extend(chunk)
                    if len(audio) > 20_000_000:
                        raise ProviderError("Cloud speech exceeded 20 MB safety limit.")
                return bytes(audio)
        except httpx.HTTPError as exc:
            raise ProviderError("Cloud speech request failed. Try local speech.") from exc
