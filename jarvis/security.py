"""Windows DPAPI secrets and conservative filesystem capabilities."""
import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path
import re
import stat

def gemini_key(vault):
    """Read the key without importing the large provider SDK on the UI thread."""
    from .config import ENDPOINTS
    return os.environ.get("GEMINI_API_KEY", "").strip() or vault.get("chat:gemini", ENDPOINTS["gemini"]) or vault.get("chat:gemini", "https://generativelanguage.googleapis.com/v1beta/openai")

class SecretVault:
    def __init__(self, directory: Path):
        self.directory = directory / "credentials"

    def _path(self, purpose, endpoint):
        return self.directory / (hashlib.sha256((purpose + "|" + endpoint).encode()).hexdigest() + ".bin")

    @staticmethod
    def _crypt(data: bytes, decrypt=False):
        if os.name != "nt":
            raise RuntimeError("Credential storage requires Windows DPAPI; no plaintext fallback is provided.")
        class Blob(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]
        buffer = ctypes.create_string_buffer(data)
        source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
        target = Blob()
        crypt = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
        fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        fn.restype = wintypes.BOOL
        if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
            raise OSError(ctypes.get_last_error(), "Windows could not protect/unprotect the credential.")
        try:
            return ctypes.string_at(target.data, target.size)
        finally:
            kernel.LocalFree(target.data)

    def get(self, purpose, endpoint):
        path = self._path(purpose, endpoint)
        return self._crypt(path.read_bytes(), True).decode() if path.exists() else ""

    def set(self, purpose, endpoint, secret):
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(purpose, endpoint)
        protected = self._crypt(secret.encode())
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(protected)
        temporary.replace(path)

    def delete(self, purpose, endpoint):
        self._path(purpose, endpoint).unlink(missing_ok=True)

    def clear(self):
        if self.directory.exists():
            for path in self.directory.glob("*.bin"):
                path.unlink()

SENSITIVE = {".env", ".aws", ".ssh", ".gnupg", ".git", ".azure", ".docker", ".npmrc", ".pypirc", ".netrc", ".git-credentials", "credentials", "credentials.json", "secrets.json", "id_rsa", "id_ed25519"}
TEXT_EXTENSIONS = {".txt", ".md", ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".scss", ".php", ".sql", ".json", ".yaml", ".yml", ".toml", ".ini", ".xml", ".csv", ".log"}

class FilePolicy:
    def __init__(self, roots, private_dir=None):
        self.roots = [Path(root).resolve(strict=True) for root in roots]
        self.private_dir = Path(private_dir).resolve() if private_dir else None

    def check(self, value: str, exists=True) -> Path:
        raw = Path(value)
        if not raw.is_absolute() or len(value) > 1024:
            raise PermissionError("Use an absolute path inside an approved folder.")
        # Reject alternate streams, device paths and reparse points, including junctions.
        if os.name == "nt" and (value.startswith(("\\\\", "//")) or ":" in value[2:]):
            raise PermissionError("Network/device paths and alternate data streams are blocked.")
        for component in (raw, *raw.parents):
            if component.exists() or component.is_symlink():
                info = component.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise PermissionError("Links and junctions are blocked.")
        path = raw.resolve(strict=exists)
        if not any(path.is_relative_to(root) for root in self.roots):
            raise PermissionError("This path is outside approved folders. Add its folder in Settings.")
        if self.private_dir and path.is_relative_to(self.private_dir):
            raise PermissionError("JARVIS private data is not accessible to AI tools.")
        if any(part.lower() in SENSITIVE or part.lower().startswith(".env.") for part in path.parts):
            raise PermissionError("Credential and secret paths are blocked.")
        return path

def scrub(text: str) -> str:
    text = re.sub(r"(?i)(?:sk-|sk-ant-|AIza)[A-Za-z0-9_\-]{12,}", "[REDACTED]", text)
    text = re.sub(r"(?i)((?:api[_ -]?key|password|secret|authorization)\s*[:=]\s*)[^\s,;]+", r"\1[REDACTED]", text)
    return text
