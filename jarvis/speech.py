"""Interruptible OS speech isolated from the GUI's native library lifetime."""
import base64
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from PySide6.QtCore import QObject, QProcess, Signal, Slot
from PySide6.QtTextToSpeech import QTextToSpeech

# Text never appears in subprocess arguments or a temporary file.
WINDOWS_SCRIPT = r'''
Add-Type -AssemblyName System.Speech
$payload = [Console]::In.ReadToEnd() | ConvertFrom-Json
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    if ($payload.voice) { $speaker.SelectVoice($payload.voice) }
    $speaker.Rate = [int]$payload.rate
    $speaker.Volume = [int]$payload.volume
    $speaker.Speak([string]$payload.text)
} finally { $speaker.Dispose() }
'''

@dataclass(frozen=True)
class Voice:
    label: str
    def name(self):
        return self.label

class NativeSpeech(QObject):
    stateChanged = Signal(object)
    errorOccurred = Signal(object, str)
    voicesChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.rate, self.volume, self.voice = 0.0, 0.8, ""
        self._state = QTextToSpeech.State.Ready
        self.serial = 0
        self.voices = [Voice("System default")]
        self.inventory = QProcess(self)
        self.inventory.finished.connect(self._voices_ready)
        if sys.platform == "win32":
            from .tools import windows_executable
            executable = str(Path(windows_executable("cmd.exe")).parent / "WindowsPowerShell/v1.0/powershell.exe")
            script = "Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; @($s.GetInstalledVoices() | ForEach-Object {$_.VoiceInfo.Name}) | ConvertTo-Json -Compress; $s.Dispose()"
            encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
            self.inventory.start(executable, ["-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", encoded])
        elif sys.platform == "darwin":
            self.inventory.start("/usr/bin/say", ["-v", "?"])

    @Slot(int, QProcess.ExitStatus)
    def _voices_ready(self, code, status):
        if code != 0:
            return
        output = bytes(self.inventory.readAllStandardOutput()).decode("utf-8", errors="replace")
        try:
            if sys.platform == "win32":
                names = json.loads(output)
                names = names if isinstance(names, list) else [names]
            else:
                import re
                names = [re.split(r"\s+[a-z]{2}_[A-Z]{2}\s", row, maxsplit=1)[0].strip() for row in output.splitlines() if row.strip()]
            self.voices = [Voice("System default")] + [Voice(name) for name in names if isinstance(name, str)]
            self.voicesChanged.emit()
        except (ValueError, TypeError):
            pass

    def availableVoices(self):
        return self.voices

    def setVoice(self, voice):
        self.voice = "" if voice.name() == "System default" else voice.name()

    def setRate(self, value):
        self.rate = max(-1.0, min(1.0, value))

    def setVolume(self, value):
        self.volume = max(0.0, min(1.0, value))

    def state(self):
        return self._state

    def _transition(self, state):
        self._state = state
        self.stateChanged.emit(state)

    def say(self, text):
        self.stop()
        self.serial += 1
        token = self.serial
        process = QProcess(self)
        self.process = process
        if sys.platform == "win32":
            from .tools import windows_executable
            executable = str(Path(windows_executable("cmd.exe")).parent / "WindowsPowerShell/v1.0/powershell.exe")
            encoded = base64.b64encode(WINDOWS_SCRIPT.encode("utf-16le")).decode("ascii")
            arguments = ["-NoLogo", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", encoded]
            payload = json.dumps({"text": text, "voice": self.voice, "rate": round(self.rate * 10), "volume": round(self.volume * 100)}, ensure_ascii=True).encode("utf-8")
        elif sys.platform == "darwin":
            executable = "/usr/bin/say"
            arguments = ["-r", str(round(180 * (1 + self.rate * .6))), "-f", "-"]
            if self.voice:
                arguments += ["-v", self.voice]
            payload = (f"[[volm {self.volume}]]" + text).encode("utf-8")
        else:
            process.deleteLater()
            self.process = None
            self.errorOccurred.emit(None, "Local speech supports Windows and macOS.")
            return
        process.setProperty("speech_token", token)
        process.finished.connect(self._speech_finished)
        process.errorOccurred.connect(self._speech_error)
        process.start(executable, arguments)
        process.write(payload)
        process.closeWriteChannel()
        self._transition(QTextToSpeech.State.Speaking)

    @Slot(int, QProcess.ExitStatus)
    def _speech_finished(self, code, status):
        process = self.sender()
        if process.property("speech_token") == self.serial:
            self.process = None
            if code != 0:
                self.errorOccurred.emit(None, "Native speech failed. Check your OS speech voice and default output device.")
            self._transition(QTextToSpeech.State.Ready)
        process.deleteLater()

    @Slot(QProcess.ProcessError)
    def _speech_error(self, error):
        process = self.sender()
        if process.property("speech_token") == self.serial:
            self.errorOccurred.emit(error, "Could not start native speech.")
            self.process = None
            self._transition(QTextToSpeech.State.Ready)
        if error == QProcess.ProcessError.FailedToStart:
            process.deleteLater()

    def stop(self):
        self.serial += 1
        process, self.process = self.process, None
        if process:
            process.kill()
            process.waitForFinished(1000)
        if self._state != QTextToSpeech.State.Ready:
            self._transition(QTextToSpeech.State.Ready)

    def close(self):
        self.stop()
        if self.inventory.state() != QProcess.ProcessState.NotRunning:
            self.inventory.kill()
            self.inventory.waitForFinished(1000)

def local_speech(parent):
    return NativeSpeech(parent)
