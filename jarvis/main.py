import logging
from logging.handlers import RotatingFileHandler
import sys
import traceback
import faulthandler
from datetime import datetime
from PySide6.QtWidgets import QApplication, QMessageBox
from .config import data_dir
from .security import SecretVault
from .storage import Store

_native_trace = None

def configure_logging(directory):
    global _native_trace
    logs = directory / "logs"
    logs.mkdir(exist_ok=True)
    handler = RotatingFileHandler(logs / "crash.log", maxBytes=256000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger = logging.getLogger("jarvis")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    faulthandler.disable()
    if _native_trace:
        _native_trace.close()
    # Native failures cannot be handled by sys.excepthook. Keep stack locations only.
    for old in sorted(logs.glob("native-*.log"))[:-2]:
        try:
            old.unlink()
        except OSError:
            pass
    _native_trace = (logs / ("native-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".log")).open("w")
    faulthandler.enable(_native_trace, all_threads=True)
    def crash(kind, value, tb):
        # Log only stack locations and exception class; messages/locals may contain secrets.
        frames = "\n".join(f"{frame.filename}:{frame.lineno} in {frame.name}" for frame in traceback.extract_tb(tb))
        logger.error("Unhandled %s\n%s", kind.__name__, frames)
        QMessageBox.critical(None, "JARVIS encountered an error", "An unexpected error occurred. Sanitized stack locations were saved to local diagnostics. Restart JARVIS if needed.")
    sys.excepthook = crash

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("JARVIS")
    app.setOrganizationName("ASH")
    directory = data_dir()
    from PySide6.QtCore import QLockFile
    instance_lock = QLockFile(str(directory / "instance.lock"))
    if not instance_lock.tryLock(0):
        QMessageBox.information(None, "JARVIS already running", "Close the existing JARVIS window before opening another instance. This prevents competing microphone streams.")
        return 0
    configure_logging(directory)
    startup_trace = None
    if "--smoke-test" in sys.argv:
        import faulthandler
        startup_trace = (directory / "logs" / "startup-trace.log").open("w")
        faulthandler.dump_traceback_later(15, repeat=True, file=startup_trace)
    # Remove abandoned cloud speech files from an earlier crash, never user screenshots.
    for path in (directory / "audio-cache").glob("*.wav"):
        try:
            path.unlink()
        except OSError:
            pass
    from .ui import Window
    try:
        window = Window(Store.open_recover(directory / "jarvis.sqlite3"), SecretVault(directory), directory)
    except Exception:
        logging.getLogger("jarvis").error("Startup failed; check settings database and audio installation.")
        QMessageBox.critical(None, "Startup failed", "JARVIS could not load. Check your Python dependencies and local settings database. See README recovery steps.")
        return 1
    if startup_trace:
        faulthandler.cancel_dump_traceback_later()
    if window.settings.start_minimized:
        window.showMinimized()
    else:
        window.show()
    if "--smoke-test" in sys.argv:
        from PySide6.QtCore import QTimer
        if "--lifecycle-test" in sys.argv:
            actions = [window.wake, window.sleep, lambda: window.hard_mute_button.setChecked(True), lambda: window.hard_mute_button.setChecked(False), window.stop_all]
            for step in range(20):
                QTimer.singleShot(1000 + step * 700, actions[step % len(actions)])
        def verify_launch():
            import json
            import platform
            from .audio import Microphone
            from .tools import system_info
            model = Microphone()
            model.offline(b"", window.settings.vosk_model)
            report = {"platform": platform.platform(), "state": window.state,
                "windows_voices": [v.name() for v in window.tts.availableVoices()],
                "vosk_loaded": True, "jarvis_in_vocabulary": model._model.vosk_model_find_word("jarvis") >= 0,
                "microphone_capture_started": False, "api_requests": 0,
                "system_metrics_available": bool(system_info())}
            import psutil
            report["process_rss_mb"] = round(psutil.Process().memory_info().rss / 2**20, 1)
            report["lifecycle_cycles"] = 4 if "--lifecycle-test" in sys.argv else 0
            window.grab().save(str(directory / "window.png"))
            (directory / "launch-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            window.close()
            app.quit()
        QTimer.singleShot(30000 if "--lifecycle-test" in sys.argv else 1000, verify_launch)
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
