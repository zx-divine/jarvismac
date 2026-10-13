"""Render the actual desktop window and exercise local TTS; no microphone or API use."""
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["QT_QPA_PLATFORM"] = ("cocoa" if sys.platform == "darwin" else "windows") if "--native" in sys.argv else "offscreen"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from PySide6.QtTextToSpeech import QTextToSpeech
from jarvis.storage import Store
from jarvis.security import SecretVault
from jarvis.ui import Window

directory = Path(__file__).resolve().parents[1] / (".native-desktop-check" if "--native" in sys.argv else ".test-data/desktop")
directory.mkdir(parents=True, exist_ok=True)
app = QApplication([])
window = Window(Store(directory / "db.sqlite"), SecretVault(directory), directory)
window.show()
states = []
window.tts.stateChanged.connect(lambda state: states.append(state.name))
def inspect():
    window.grab().save(str(directory / "standby.png"))
    print("Window rendered:", directory / "standby.png")
    print("Local voices:", [v.name() for v in window.tts.availableVoices()])
    if "--voice" in sys.argv:
        window.wake()
    else:
        window.mute_button.setChecked(True)
        window.wake()
    window.show_page(3)
    window.grab().save(str(directory / "settings.png"))
    window.show_page(0)
    window.quick("system_info", {}) if "--voice" not in sys.argv else None
def finish():
    print("TTS transitions:", states)
    print("Final UI state:", window.state)
    window.close()
    app.quit()
QTimer.singleShot(500, inspect)
QTimer.singleShot(7000 if "--voice" in sys.argv else 2000, finish)
raise SystemExit(app.exec())
