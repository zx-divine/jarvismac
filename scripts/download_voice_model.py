"""Download a small official English Vosk model; validate archive paths before extraction."""
from pathlib import Path
import shutil
import urllib.request
import zipfile

URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"

def main():
    destination = Path(__file__).resolve().parents[1] / "models"
    destination.mkdir(exist_ok=True)
    archive = destination / "download.zip"
    try:
        request = urllib.request.Request(URL, headers={"User-Agent": "ASH-JARVIS-Setup/0.1"})
        with urllib.request.urlopen(request, timeout=60) as response, archive.open("wb") as output:
            total = 0
            while data := response.read(1024 * 1024):
                total += len(data)
                if total > 100_000_000:
                    raise ValueError("Model archive exceeds 100 MB limit.")
                output.write(data)
        with zipfile.ZipFile(archive) as zipped:
            if sum(item.file_size for item in zipped.infolist()) > 300_000_000:
                raise ValueError("Extracted model exceeds 300 MB limit.")
            for item in zipped.infolist():
                target = (destination / item.filename).resolve()
                if not target.is_relative_to(destination.resolve()) or (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Unsafe path/link in voice model archive.")
            zipped.extractall(destination)
        print("Installed:", destination / "vosk-model-small-en-us-0.15")
        print("Select this model in Settings, approve microphone access, and enable the local wake detector.")
    finally:
        archive.unlink(missing_ok=True)

if __name__ == "__main__":
    main()
