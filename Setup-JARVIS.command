#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "Use a native Apple Silicon macOS terminal."
  exit 1
fi
bash scripts/setup_macos.sh
