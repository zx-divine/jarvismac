#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "Build requires native Apple Silicon macOS, not Windows or Rosetta."
  exit 1
fi
PYTHON="${JARVIS_PYTHON:-python3.12}"
"$PYTHON" -c 'import platform; assert platform.machine() == "arm64", "Use native arm64 Python"'
"$PYTHON" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-macos-dev.txt
.venv/bin/python -m pip check
.venv/bin/python -m pytest -q
.venv/bin/python scripts/download_voice_model.py
# A real load validates the universal2 Vosk native library and bundled model.
.venv/bin/python -c 'from jarvis.audio import Microphone; from jarvis.config import default_voice_model; Microphone().offline(b"", default_voice_model())'
.venv/bin/python -m PyInstaller --noconfirm --clean packaging/JARVIS-mac.spec
/usr/bin/file dist/JARVIS.app/Contents/MacOS/JARVIS
/usr/bin/codesign --verify --deep --strict dist/JARVIS.app
JARVIS_DATA_DIR="$PWD/.test-data/mac-package" dist/JARVIS.app/Contents/MacOS/JARVIS --smoke-test
/usr/bin/ditto -c -k --sequesterRsrc --keepParent dist/JARVIS.app dist/JARVIS-macos-arm64.zip
echo "Built and smoke-tested dist/JARVIS.app on this macOS host. This is ad-hoc signed, not Developer ID notarized. Live microphone/automation acceptance still requires the owner's Mac."
