#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "Use a native Apple Silicon macOS terminal."
  exit 1
fi
if [[ -d dist/JARVIS.app ]]; then
  exec /usr/bin/open dist/JARVIS.app
elif [[ -x .venv/bin/python ]]; then
  exec .venv/bin/python -m jarvis
else
  echo "Run Setup-JARVIS.command first, then Start-JARVIS.command."
  exit 1
fi
