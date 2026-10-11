from dataclasses import asdict, dataclass, field
from pathlib import Path
import os
from urllib.parse import urlsplit

ENDPOINTS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "gemini": "https://generativelanguage.googleapis.com",
    "compatible": "https://api.openai.com/v1",
}

def data_dir() -> Path:
    root = Path(os.environ.get("JARVIS_DATA_DIR") or (Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ASH-JARVIS"))
    root.mkdir(parents=True, exist_ok=True)
    return root

def validate_endpoint(url: str) -> str:
    value = url.rstrip("/")
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("API endpoints must be HTTPS URLs without embedded credentials, queries or fragments.")
    return value

def default_voice_model():
    folder = Path(__file__).resolve().parents[1] / "models" / "vosk-model-small-en-us-0.15"
    return str(folder) if folder.is_dir() else ""

@dataclass
class Settings:
    provider: str = "gemini"
    model: str = ""
    endpoint: str = ENDPOINTS["gemini"]
    audio_endpoint: str = ENDPOINTS["openai"]
    transcription_model: str = "whisper-1"
    speech_model: str = "tts-1"
    speech_voice: str = "alloy"
    speech_mode: str = "local"
    local_voice: str = ""
    speech_enabled: bool = False
    voice_rate: float = 0.0
    voice_volume: float = 0.8
    mic_enabled: bool = False
    mic_device: int | None = None
    speaker_device: str = ""
    recognition: str = "gemini"
    vosk_model: str = field(default_factory=default_voice_model)
    continuous: bool = False
    wake_word: bool = False
    hard_mute: bool = False
    vad_threshold: float = 0.012
    language: str = "auto"
    remember_history: bool = False
    retention_days: int = 30
    context_chars: int = 24000
    approved_folders: list[str] = field(default_factory=list)
    disabled_tools: list[str] = field(default_factory=list)
    developer_mode: bool = False
    low_power: bool = True
    theme: str = "cyan"
    start_minimized: bool = False

    def validate(self):
        if self.provider not in ENDPOINTS:
            raise ValueError("Unknown AI provider.")
        self.endpoint = validate_endpoint(self.endpoint)
        if self.provider == "gemini":
            if self.endpoint == "https://generativelanguage.googleapis.com/v1beta/openai":
                self.endpoint = ENDPOINTS["gemini"]
            if self.endpoint != ENDPOINTS["gemini"]:
                raise ValueError("Native Gemini uses the official Google endpoint. Use the compatible provider for custom endpoints.")
        self.audio_endpoint = validate_endpoint(self.audio_endpoint)
        if not 1 <= self.retention_days <= 3650 or not 4000 <= self.context_chars <= 100000:
            raise ValueError("Invalid retention or context size.")
        if not -1 <= self.voice_rate <= 1 or not 0 <= self.voice_volume <= 1:
            raise ValueError("Invalid voice speed or volume.")
        if not 0.001 <= self.vad_threshold <= 0.2:
            raise ValueError("Voice activity threshold must be between 0.001 and 0.2.")
        if self.speech_mode not in {"local", "cloud"} or self.recognition not in {"cloud", "gemini", "vosk"}:
            raise ValueError("Unknown speech service.")
        if self.continuous and self.recognition != "vosk":
            raise ValueError("Continuous offline mode requires Vosk recognition.")
        if self.continuous and self.wake_word:
            raise ValueError("Choose either continuous listening or wake word mode.")
        self.approved_folders = [str(Path(p).resolve(strict=True)) for p in self.approved_folders if Path(p).is_dir()]

    def to_dict(self):
        return asdict(self)
