import time
import pytest
from PySide6.QtCore import QProcess
from PySide6.QtTextToSpeech import QTextToSpeech
from PySide6.QtTest import QTest
from jarvis.storage import Store
from jarvis.speech import NativeSpeech
from jarvis.audio import Microphone
from jarvis.offline import local_command

def test_corrupted_database_preserved(tmp_path):
    path = tmp_path / "state.sqlite3"
    path.write_bytes(b"corrupt fixture, no private data")
    store = Store.open_recover(path)
    assert not store.settings().mic_enabled
    assert list(tmp_path.glob("*.recovered-*"))[0].read_bytes() == b"corrupt fixture, no private data"

def test_invalid_settings_safe_defaults_without_deletion(tmp_path):
    store = Store(tmp_path / "state.sqlite3")
    with store.connection() as db:
        db.execute("INSERT INTO settings VALUES('config','invalid json')")
    assert not store.settings().mic_enabled
    with store.connection() as db:
        assert db.execute("SELECT value FROM settings").fetchone()[0] == "invalid json"

def test_microphone_stop_before_start_never_opens(monkeypatch):
    mic = Microphone()
    mic.stop()
    monkeypatch.setattr("jarvis.audio.sd.query_devices", lambda *args: pytest.fail("capture after mute"))
    assert mic.capture(None, lambda value: None) == b""

def test_invalid_input_format(monkeypatch):
    monkeypatch.setattr("jarvis.audio.sd.query_devices", lambda *args: {"default_samplerate": 0, "max_input_channels": 0})
    with pytest.raises(RuntimeError, match="supported mono"):
        Microphone().capture(None, lambda value: None)

def test_offline_commands_exact_allowlist():
    assert local_command("Jarvis, open calculator") == ("open_app", {"app": "calculator"})
    assert local_command("system status") == ("system_info", {})
    assert local_command("open calculator; delete files") is None
    assert local_command("run powershell") is None

def test_native_speech_interrupt_regression(qapp):
    # Real OS native speech process; the old Qt SAPI path crashed on the first stop.
    speech = NativeSpeech()
    failures = []
    speech.errorOccurred.connect(lambda *args: failures.append(args))
    try:
        for _ in range(4):
            speech.say("JARVIS interruption regression test.")
            QTest.qWait(100)
            process = speech.process
            speech.stop()
            assert speech.state() == QTextToSpeech.State.Ready
            assert process.state() == QProcess.ProcessState.NotRunning
        assert not failures
    finally:
        speech.close()
