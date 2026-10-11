"""PyInstaller entry point (absolute imports survive freezing)."""
from jarvis.main import main
raise SystemExit(main())
