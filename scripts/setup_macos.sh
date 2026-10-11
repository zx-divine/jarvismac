#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "Use a native Apple Silicon macOS terminal."
  exit 1
fi
PYTHON="${JARVIS_PYTHON:-python3.12}"
"$PYTHON" -c 'import platform; assert platform.machine() == "arm64", "Use native arm64 Python"'
"$PYTHON" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-macos.txt
.venv/bin/python scripts/download_voice_model.py
echo "Launch with: .venv/bin/python -m jarvis"
