"""Native lifecycle stress probe; captures only local state, never audio contents."""
import faulthandler
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from jarvis.config import Settings
from jarvis.security import SecretVault
from jarvis.storage import Store
from jarvis.ui import Window

root = Path(os.environ.get("JARVIS_DATA_DIR", ".recovery/probe")).resolve()
root.mkdir(parents=True, exist_ok=True)
trace = (root / "native-trace.log").open("w")
faulthandler.enable(trace, all_threads=True)
app = QApplication(sys.argv)
store = Store(root / "probe.sqlite3")
settings = Settings()
if "--microphone" in sys.argv:
    settings.mic_enabled = settings.wake_word = True
    settings.recognition = "vosk"
store.save_settings(settings)
w = Window(store, SecretVault(root), root)
w.show()
started = time.monotonic()
step = 0
def tick():
    global step
    print("step", step, w.session.state, flush=True)
    if step >= 20:
        w.close()
        app.quit()
        return
    actions = [w.wake, w.sleep, lambda: w.hard_mute_button.setChecked(True), lambda: w.hard_mute_button.setChecked(False), w.stop_all]
    actions[step % len(actions)]()
    step += 1
timer = QTimer()
timer.timeout.connect(tick)
timer.start(700)
code = app.exec()
print(json.dumps({"exit": code, "steps": step, "elapsed": round(time.monotonic() - started, 2)}), flush=True)
