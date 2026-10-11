import dataclasses
import json
from pathlib import Path
import time
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QFont, QTextCursor, QCloseEvent
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QPlainTextEdit, QLineEdit, QStackedWidget, QProgressBar, QListWidget,
    QFileDialog, QMessageBox, QInputDialog, QComboBox, QSplitter, QScrollArea, QLayout)
from PySide6.QtTextToSpeech import QTextToSpeech
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QMediaDevices
from .config import Settings
from .engine import Engine
from .tools import Registry, system_info
from .audio import Microphone, transcribe, transcribe_pcm, synthesize
from .worker import Service
from .settings_ui import SettingsPanel
from .orb import CoreOrb
from .security import scrub, gemini_key
from .session import Session, State, control_phrase
from .listener import LocalListener
from .speech import local_speech
from .offline import local_command
import sys

STYLE = """
QWidget { background: #080f1c; color: #d7e6f5; font-family: 'Segoe UI'; font-size: 13px; }
QMainWindow { background: #080f1c; }
QLabel#brand { color: #39dfff; font-size: 27px; font-weight: 600; letter-spacing: 3px; }
QLabel#muted { color: #7d9bb6; }
QPushButton { background: #112237; border: 1px solid #24445d; border-radius: 7px; padding: 9px 13px; }
QPushButton:hover { background: #17334b; border-color: #39dfff; }
QPushButton:disabled { color: #52677a; border-color: #172534; }
QPushButton#primary { color: #07121b; background: #36d7f4; font-weight: 600; }
QPushButton:checked { border: 1px solid #39dfff; color: #39dfff; }
QLineEdit, QPlainTextEdit, QListWidget, QComboBox, QSpinBox, QDoubleSpinBox { background: #0d1929; border: 1px solid #22394e; border-radius: 6px; padding: 7px; selection-background-color: #235473; }
QPlainTextEdit { font-size: 14px; }
QProgressBar { background: #132237; border: 0; border-radius: 3px; text-align: center; height: 13px; color: #d7e6f5; }
QProgressBar::chunk { background: #21a9ce; border-radius: 3px; }
QTabBar::tab { background: #112237; padding: 10px; border: 1px solid #20394d; }
QTabBar::tab:selected { color: #39dfff; }
QScrollBar:vertical { background: #0d1929; width: 10px; }
QScrollBar::handle:vertical { background: #284256; min-height: 25px; }
QSplitter::handle { background: #182e41; }
QScrollArea { border: 0; }
"""

class Window(QMainWindow):
    def __init__(self, store, vault, directory):
        super().__init__()
        self.store, self.vault, self.directory = store, vault, Path(directory)
        self.settings = store.settings()
        store.prune(self.settings.retention_days)
        self.registry = Registry(self.settings, self.directory)
        self.session = Session(self.settings.hard_mute)
        self.task_generation = 0
        self.listener = None
        self.retired_listeners = []
        self.closing = False
        self.approval_dialog = None
        self.engine = Engine(self.settings, vault, store, self.registry)
        self.service = Service()
        self.service.validity = self.session.valid
        self.microphone = Microphone()
        self.history, self.cid = [], None
        self.busy, self.task_kind, self.state = False, "", "idle"
        self.background_listening, self.awaiting_wake_query = False, False
        self.pending_send, self.pending_speech = "", ""
        self.token_count, self.buffer = 0, ""
        self.audio_file = None
        self.local_speaking = False
        self.voice_error_count = 0
        self.setWindowTitle("J.A.R.V.I.S. · ASH's personal assistant")
        self.resize(1240, 810)
        self.setMinimumSize(940, 650)
        self.setStyleSheet(STYLE)
        central = QWidget()
        outer = QHBoxLayout(central)
        outer.setContentsMargins(20, 18, 20, 18)
        splitter = QSplitter()
        outer.addWidget(splitter)
        self.setCentralWidget(central)
        sidebar = QWidget()
        side = QVBoxLayout(sidebar)
        brand = QLabel("J.A.R.V.I.S.")
        brand.setObjectName("brand")
        side.addWidget(brand)
        subtitle = QLabel("PERSONAL SYSTEM  /  ASH")
        subtitle.setObjectName("muted")
        side.addWidget(subtitle)
        self.orb = CoreOrb()
        side.addWidget(self.orb)
        self.status = QLabel("IDLE · microphone off")
        self.status.setWordWrap(True)
        side.addWidget(self.status)
        self.provider_status = QLabel()
        self.provider_status.setWordWrap(True)
        self.provider_status.setObjectName("muted")
        side.addWidget(self.provider_status)
        self.meter = QProgressBar()
        self.meter.setRange(0, 100)
        self.meter.setValue(0)
        self.meter.setFormat("Microphone %p%")
        side.addWidget(self.meter)
        self.mic_button = QPushButton("Hold to talk")
        self.mic_button.pressed.connect(self.start_capture)
        self.mic_button.released.connect(self.microphone.stop)
        side.addWidget(self.mic_button)
        self.listen_button = QPushButton("Start offline listening")
        self.listen_button.setCheckable(True)
        self.listen_button.clicked.connect(self.toggle_listening)
        side.addWidget(self.listen_button)
        self.stop_button = QPushButton("Interrupt / stop all")
        self.stop_button.clicked.connect(self.stop_all)
        side.addWidget(self.stop_button)
        self.mute_button = QPushButton("Mute spoken replies")
        self.mute_button.setCheckable(True)
        self.mute_button.toggled.connect(lambda muted: self.stop_speech() if muted else None)
        side.addWidget(self.mute_button)
        wake = QPushButton("Wake JARVIS")
        wake.clicked.connect(self.wake)
        side.addWidget(wake)
        sleep = QPushButton("Put JARVIS to Sleep")
        sleep.clicked.connect(self.sleep)
        side.addWidget(sleep)
        self.hard_mute_button = QPushButton("Hard Mute")
        self.hard_mute_button.setCheckable(True)
        self.hard_mute_button.setChecked(self.settings.hard_mute)
        self.hard_mute_button.toggled.connect(self.hard_mute)
        side.addWidget(self.hard_mute_button)
        stop_speaking = QPushButton("Stop Speaking")
        stop_speaking.clicked.connect(self.stop_speech)
        side.addWidget(stop_speaking)
        self.stop_button.setText("Stop all")
        self.mute_button.setText("Mute replies")
        sleep.setText("Sleep")
        for first, second in [(self.stop_button, self.mute_button), (wake, sleep), (self.hard_mute_button, stop_speaking)]:
            side.removeWidget(first)
            side.removeWidget(second)
            controls = QHBoxLayout()
            controls.addWidget(first)
            controls.addWidget(second)
            side.addLayout(controls)
        side.addStretch()
        self.metrics = {}
        for key, label in [("cpu_percent", "CPU"), ("ram_percent", "RAM"), ("disk_percent", "SSD")]:
            bar = QProgressBar()
            bar.setFormat(label + "  %p%")
            self.metrics[key] = bar
            side.addWidget(bar)
        self.battery = QLabel("Battery: reading…")
        side.addWidget(self.battery)
        self.tokens = QLabel("Session API tokens: 0")
        side.addWidget(self.tokens)
        side.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        sidebar_scroll = QScrollArea()
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sidebar_scroll.setWidget(sidebar)
        splitter.addWidget(sidebar_scroll)
        content = QWidget()
        column = QVBoxLayout(content)
        nav = QHBoxLayout()
        column.addLayout(nav)
        self.pages = QStackedWidget()
        column.addWidget(self.pages)
        self.nav_buttons = []
        for label in ("Chat", "Developer", "History", "Settings", "Memory & security", "Logs"):
            button = QPushButton(label)
            index = len(self.nav_buttons)
            button.clicked.connect(lambda checked=False, i=index: self.show_page(i))
            button.setCheckable(True)
            nav.addWidget(button)
            self.nav_buttons.append(button)
        self.build_chat()
        self.build_developer()
        self.build_history()
        self.settings_panel = SettingsPanel(self.settings, vault, directory)
        self.settings_panel.awake_guard = lambda: self.session.state != State.SLEEPING
        self.settings_panel.token_reader = lambda: self.session.generation
        self.settings_panel.model_service.validity = self.session.valid
        self.settings_panel.saved.connect(self.apply_settings)
        self.pages.addWidget(self.settings_panel)
        self.build_privacy()
        self.build_diagnostics()
        splitter.addWidget(content)
        splitter.setSizes([260, 940])
        self.tts = local_speech(self)
        self.tts.voicesChanged.connect(self.configure_voice)
        self.tts.stateChanged.connect(self.tts_state)
        self.tts.errorOccurred.connect(lambda reason, text: self.voice_error("Local speech: " + text))
        self.player = QMediaPlayer(self)
        self.output = QAudioOutput(self)
        self.player.setAudioOutput(self.output)
        self.player.playbackStateChanged.connect(self.player_state)
        self.player.errorOccurred.connect(lambda error, text: self.voice_error("Audio playback: " + text))
        self.service.event.connect(self.service_event)
        self.service.approval.connect(self.approve)
        self.service.level.connect(self.audio_level)
        self.metrics_timer = QTimer(self)
        self.metrics_timer.timeout.connect(self.refresh_metrics)
        self.metrics_timer.start(2000)
        self.flush_timer = QTimer(self)
        self.flush_timer.timeout.connect(self.flush_text)
        self.flush_timer.start(50)
        self.refresh_metrics()
        self.configure_voice()
        self.refresh_provider()
        self.refresh_history()
        self.refresh_memories()
        self.refresh_commands()
        self.show_page(0)
        self.write("JARVIS · Standing by, ASH. Press Wake JARVIS to begin.\nConfigure Gemini and verify available models in Settings. Local quick commands work while awake without an API key.\nEnable the offline detector and approve microphone access for local voice wake/sleep.\n\n")
        self.set_state("sleeping", "STANDBY")
        self.log("Application started in standby. No cloud requests made.")
        self.start_listener()

    def build_chat(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.chat = QPlainTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setPlaceholderText("Your conversation with JARVIS")
        layout.addWidget(self.chat)
        quick = QHBoxLayout()
        for label, tool, args in [("System status", "system_info", {}), ("VS Code", "open_app", {"app": "vscode"}), ("Finder" if sys.platform == "darwin" else "Explorer", "open_app", {"app": "explorer"}), ("System Settings" if sys.platform == "darwin" else "Windows Settings", "open_app", {"app": "settings"}), ("Abort shutdown", "power", {"action": "abort"})]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, n=tool, a=args: self.quick(n, a))
            quick.addWidget(button)
        layout.addLayout(quick)
        self.input = QPlainTextEdit()
        self.input.setMaximumHeight(110)
        self.input.setPlaceholderText("Speak or type, ASH. English, हिन्दी or Hinglish. Paste code here.")
        layout.addWidget(self.input)
        actions = QHBoxLayout()
        self.send_button = QPushButton("Send to JARVIS")
        self.send_button.setObjectName("primary")
        self.send_button.clicked.connect(self.send)
        actions.addWidget(self.send_button)
        new = QPushButton("New conversation")
        new.clicked.connect(self.new_chat)
        actions.addWidget(new)
        layout.addLayout(actions)
        self.pages.addWidget(page)

    def build_developer(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        note = QLabel("DEVELOPER WORKSPACE\nChoose approved files and projects. Existing source files are never modified by JARVIS. Review suggested patches and commit or back up your project before applying changes. Development commands may execute project code.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.project = QLineEdit()
        self.project.setPlaceholderText("Absolute approved project folder")
        layout.addWidget(self.project)
        choose = QPushButton("Choose project folder")
        choose.clicked.connect(lambda: self.select_path(self.project, True))
        layout.addWidget(choose)
        open_project = QPushButton("Open in VS Code")
        open_project.clicked.connect(lambda: self.quick("open_project", {"path": self.project.text(), "editor": "vscode"}))
        layout.addWidget(open_project)
        self.source_file = QLineEdit()
        self.source_file.setPlaceholderText("Absolute selected source file")
        layout.addWidget(self.source_file)
        choose_file = QPushButton("Choose source file")
        choose_file.clicked.connect(lambda: self.select_path(self.source_file, False))
        layout.addWidget(choose_file)
        self.code_task = QComboBox()
        self.code_task.addItems(["Explain this code", "Review this code for bugs", "Review website security", "Suggest a patch without changing files"])
        layout.addWidget(self.code_task)
        explain = QPushButton("Ask JARVIS about the selected file")
        explain.clicked.connect(self.ask_about_file)
        layout.addWidget(explain)
        self.dev_command = QComboBox()
        for label, value in [("git status", "git_status"), ("git diff", "git_diff"), ("Python: pytest -q", "pytest"), ("npm test -- --watch=false", "npm_test")]:
            self.dev_command.addItem(label, value)
        layout.addWidget(self.dev_command)
        run = QPushButton("Review and run development command")
        run.clicked.connect(lambda: self.quick("dev_command", {"directory": self.project.text(), "command": self.dev_command.currentData()}))
        layout.addWidget(run)
        layout.addStretch()
        self.pages.addWidget(page)

    def build_history(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Conversation storage is opt-in. Enable it in Settings. Loading history sends it to your AI provider on your next message."))
        self.history_list = QListWidget()
        layout.addWidget(self.history_list)
        load = QPushButton("Load selected conversation")
        load.clicked.connect(self.load_history)
        remove = QPushButton("Delete selected conversation")
        remove.clicked.connect(self.delete_history)
        layout.addWidget(load)
        layout.addWidget(remove)
        self.pages.addWidget(page)

    def build_privacy(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        note = QLabel("APPROVED MEMORIES\nSave only preferences you want included in future AI requests. Memories and saved history are plaintext local data. Credentials are encrypted separately. Retention applies to conversations; memories remain until you delete them.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.memory_list = QListWidget()
        layout.addWidget(self.memory_list)
        add = QPushButton("Save a preference explicitly…")
        add.clicked.connect(self.add_memory)
        remove = QPushButton("Delete selected memory")
        remove.clicked.connect(self.delete_memory)
        layout.addWidget(add)
        layout.addWidget(remove)
        layout.addWidget(QLabel("CUSTOM QUICK COMMANDS · tool + validated JSON arguments"))
        self.command_list = QListWidget()
        layout.addWidget(self.command_list)
        row = QHBoxLayout()
        for title, callback in [("Add command", self.add_command), ("Run selected", self.run_command), ("Delete selected", self.delete_command)]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        clear = QPushButton("Clear all JARVIS data, settings and credentials…")
        clear.clicked.connect(self.clear_data)
        layout.addWidget(clear)
        self.pages.addWidget(page)

    def build_diagnostics(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Session diagnostics omit conversation text, file contents and tool arguments. API error bodies are never logged."))
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        layout.addWidget(self.logs)
        export = QPushButton("Export sanitized diagnostics…")
        export.clicked.connect(self.export_diagnostics)
        layout.addWidget(export)
        test_mic = QPushButton("Test Microphone (3 seconds, local only)")
        test_mic.clicked.connect(self.test_microphone)
        layout.addWidget(test_mic)
        test_speaker = QPushButton("Test Speaker (local voice)")
        test_speaker.clicked.connect(self.test_speaker)
        layout.addWidget(test_speaker)
        self.pages.addWidget(page)

    def test_microphone(self):
        if self.busy or self.session.hard_muted or self.session.state == State.SLEEPING:
            self.log("Wake manually and leave Hard Mute before testing microphone.")
            return
        if not self.settings.mic_enabled:
            self.log("Enable microphone permission in Settings before testing.")
            return
        self.stop_listener()
        self.microphone.stop_event.clear()
        async def diagnose():
            import asyncio
            pcm = await asyncio.to_thread(self.microphone.capture, self.settings.mic_device, self.service.level.emit, 3, self.settings.vad_threshold)
            return "Microphone capture completed locally. " + ("Speech-level audio detected." if pcm else "No speech exceeded the configured threshold; inspect the meter/device/threshold.")
        self.begin("diagnostic", diagnose(), "completed")

    def test_speaker(self):
        if self.busy or self.session.state == State.SLEEPING:
            self.log("Wake manually before testing speaker.")
            return
        self.stop_speech()
        self.local_speaking = True
        self.set_state("speaking", "local speaker test")
        self.tts.say("JARVIS speaker test. Online and ready, ASH.")

    def show_page(self, index):
        self.pages.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)

    def set_state(self, state, detail=""):
        if self.session.state == State.SLEEPING and state != "sleeping":
            state, detail = "sleeping", "STANDBY"
        elif state in {"listening", "thinking", "speaking", "idle"}:
            self.session.transition(self.session.generation, State.LISTENING if state == "idle" else State(state))
        self.state = self.orb.state = state
        self.orb.timer.setInterval(250 if state == "sleeping" else 66 if self.settings.low_power else 33)
        self.orb.update()
        self.status.setText(state.upper() + (" · " + detail if detail else ""))
        if self.session.hard_muted:
            self.status.setText(self.status.text() + " · MICROPHONE OFF (HARD MUTE)")
        if state == "speaking" and self.listener:
            self.listener.pause_capture()

    def write(self, text):
        self.chat.moveCursor(QTextCursor.MoveOperation.End)
        self.chat.insertPlainText(text)
        self.chat.ensureCursorVisible()

    def receive_text(self, text):
        self.buffer += text

    def flush_text(self):
        if self.buffer:
            self.write(self.buffer)
            self.buffer = ""

    def log(self, message):
        self.logs.appendPlainText(time.strftime("%H:%M:%S") + "  " + message)

    def refresh_metrics(self):
        try:
            info = system_info()
            for key, bar in self.metrics.items():
                bar.setValue(round(info[key]))
            self.battery.setText("Battery: " + (f"{info['battery_percent']:.0f}%" + (" · charging" if info["plugged_in"] else "") if info["battery_percent"] is not None else "not available"))
        except Exception:
            self.battery.setText("System metrics unavailable")

    def refresh_provider(self):
        try:
            if self.settings.provider == "gemini":
                key = gemini_key(self.vault)
            else:
                key = self.vault.get("chat:" + self.settings.provider, self.settings.endpoint)
            configured = bool(key and self.settings.model)
        except Exception:
            configured = False
        self.provider_status.setText(f"{self.settings.provider.upper()}  /  {self.settings.model or 'choose a model'}\n" + ("Configured · connection checked on request" if configured else "SETUP REQUIRED · open Settings"))

    def begin(self, kind, coroutine, signal):
        if self.busy:
            coroutine.close()
            return False
        self.task_kind = kind
        self.task_generation = self.session.generation
        self.busy = True
        self.send_button.setEnabled(False)
        self.settings_panel.setEnabled(False)
        if not self.service.submit(coroutine, signal, self.task_generation):
            self.busy = False
            self.send_button.setEnabled(True)
            self.settings_panel.setEnabled(True)
            return False
        return True

    def send(self):
        text = self.input.toPlainText().strip()
        command = control_phrase(text)
        if command == "sleep":
            self.input.clear()
            self.sleep()
            return
        if command == "wake":
            self.input.clear()
            self.wake()
            return
        if self.session.state == State.SLEEPING:
            return
        if self.busy or not text:
            return
        offline = local_command(text)
        if offline:
            self.input.clear()
            self.quick(*offline)
            return
        if len(text) > min(16000, self.settings.context_chars):
            QMessageBox.warning(self, "Message too long", "Send a shorter message or choose one source file.")
            return
        self.stop_speech()
        self.input.clear()
        self.history.append({"role": "user", "content": text})
        if self.settings.remember_history:
            self.cid = self.cid or self.store.new_conversation()
            self.store.append(self.cid, "user", text)
        self.write("\nASH · " + text + "\n\nJARVIS · ")
        self.set_state("thinking", "contacting AI provider")
        self.show_page(0)
        token = self.session.generation
        self.begin("chat", self.engine.chat(self.history,
            lambda tool, args: self.service.approve(tool, args, token),
            lambda text: self.service.event.emit(token, "text", text),
            lambda usage: self.service.event.emit(token, "usage", usage),
            lambda name, ok: self.service.event.emit(token, "audit", (name, ok)),
            lambda: self.session.require(token)), "completed")

    def service_event(self, generation, kind, value):
        if kind == "idle":
            if generation == self.task_generation:
                self.task_idle()
            return
        if not self.session.valid(generation):
            return
        if kind == "audit":
            self.audit(*value)
        else:
            {"text": self.receive_text, "completed": self.completed, "failed": self.failed,
             "usage": self.usage, "transcript": self.transcript, "speech_audio": self.play_cloud}[kind](value)

    def completed(self, text):
        self.flush_text()
        if self.task_kind == "chat":
            self.history.append({"role": "assistant", "content": text})
            if self.settings.remember_history and self.cid:
                self.store.append(self.cid, "assistant", text)
            self.write("\n")
            self.pending_speech = text
            self.provider_status.setText(f"{self.settings.provider.upper()} · last request succeeded")
            self.refresh_history()
        else:
            self.write(text + "\n")

    def failed(self, message):
        self.flush_text()
        self.write("\n[Error] " + message + "\n")
        self.set_state("error", message[:100])
        self.log(f"{self.task_kind} failed. See the conversation panel for guidance.")
        if self.task_kind == "chat":
            self.provider_status.setText("AI request failed · local quick commands remain available")
        if self.task_kind == "listen":
            self.background_listening = False
            self.listen_button.setChecked(False)

    def task_idle(self):
        if self.closing:
            return
        self.busy = False
        self.send_button.setEnabled(True)
        self.settings_panel.setEnabled(True)
        if self.session.state == State.SLEEPING:
            self.pending_send = self.pending_speech = self.buffer = ""
            self.set_state("sleeping", "STANDBY · local wake detector only" if self.listener else "STANDBY · manual Wake")
            return
        if self.state not in {"error", "speaking"}:
            self.set_state("idle", "ready, ASH")
        if self.pending_send:
            self.input.setPlainText(self.pending_send)
            self.pending_send = ""
            token = self.session.generation
            QTimer.singleShot(100, lambda: self.send() if self.session.valid(token) and not self.session.hard_muted else None)
        elif self.pending_speech:
            text, self.pending_speech = self.pending_speech, ""
            token = self.session.generation
            QTimer.singleShot(100, lambda: self.speak(text) if self.session.valid(token) else None)
        else:
            self.start_listener()
            self.schedule_listening()

    def approve(self, generation, tool, args, answer):
        if answer.done() or not self.session.valid(generation):
            if not answer.done():
                Service.resolve(answer, False)
            return
        self.set_state("thinking", "waiting for ASH's approval")
        dialog = QMessageBox(self)
        self.approval_dialog = dialog
        dialog.setWindowTitle("Approve JARVIS action")
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        text = tool.name + "\n\n" + tool.description
        if tool.name in {"read_file", "dev_command"} and self.task_kind == "chat":
            text += "\n\nContent/output will be sent to: " + self.settings.endpoint
        if tool.name == "dev_command":
            text += "\n\nThis executes project code or reads Git state. Only approve a trusted project. The app does not sandbox development subprocesses."
        if tool.name == "power":
            text += "\n\nSave your work first. Shutdown/restart has a 60-second cancellation window."
        dialog.setText(text)
        dialog.setInformativeText(json.dumps(args, ensure_ascii=False, indent=2)[:1800])
        dialog.setDetailedText(json.dumps(args, ensure_ascii=False, indent=2))
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        approved = dialog.exec() == QMessageBox.StandardButton.Yes
        self.approval_dialog = None
        if not answer.done():
            Service.resolve(answer, approved and self.session.valid(generation))
        self.log(tool.name + (" approved by ASH" if approved else " denied by ASH"))

    def audit(self, name, ok):
        self.log(name + (" succeeded" if ok else " denied or failed"))

    def usage(self, usage):
        self.token_count += usage.get("total_tokens", usage.get("input_tokens", 0) + usage.get("output_tokens", 0))
        self.tokens.setText(f"Session API tokens: {self.token_count:,}")

    def quick(self, name, args):
        if self.busy or self.session.state == State.SLEEPING:
            return
        self.stop_speech()
        self.show_page(0)
        self.write("\nLOCAL TOOL · " + name + "\n")
        self.set_state("thinking", "local action")
        token = self.session.generation
        async def run():
            result = await self.registry.execute(name, args, lambda tool, args: self.service.approve(tool, args, token), lambda: self.session.start_action(token))
            self.service.event.emit(token, "audit", (name, result["ok"]))
            return json.dumps(result, ensure_ascii=False, indent=2)
        self.begin("tool", run(), "completed")

    def start_capture(self):
        if self.busy or self.session.hard_muted or self.session.state == State.SLEEPING:
            return
        if self.listener and self.listener.thread and self.listener.thread.is_alive():
            self.status.setText("Local listener owns the microphone. Speak your command or hard mute to stop it.")
            return
        self.stop_speech()
        self.microphone.stop_event.clear()
        self.set_state("listening", "microphone capture")
        self.begin("listen", transcribe(self.settings, self.vault, self.microphone, self.service.level.emit), "transcript")

    def audio_level(self, level):
        if self.session.hard_muted or self.closing:
            level = 0
        self.orb.level = level
        self.meter.setValue(round(level * 100))

    def transcript(self, text):
        if not text or self.session.hard_muted:
            return
        command = control_phrase(text)
        if command == "sleep":
            self.sleep()
            return
        if command == "wake":
            self.wake(from_voice=True)
            return
        if self.background_listening and self.settings.wake_word and not self.awaiting_wake_query:
            lowered = text.lower()
            marker = "hey jarvis"
            index = lowered.find(marker)
            if index < 0:
                return
            text = text[index + len(marker):].strip(" ,.!?")
            if not text:
                self.awaiting_wake_query = True
                self.write("\nJARVIS · Listening for your request, ASH.\n")
                return
        self.awaiting_wake_query = False
        self.pending_send = text

    def toggle_listening(self, enabled):
        if enabled and (not self.settings.mic_enabled or not (self.settings.continuous or self.settings.wake_word) or self.session.hard_muted):
            self.listen_button.setChecked(False)
            QMessageBox.information(self, "Offline listening setup", "Enable microphone access, configure a Vosk model and choose continuous or wake-word mode in Settings. Unmute the microphone to start.")
            return
        self.background_listening = enabled
        self.awaiting_wake_query = False
        self.listen_button.setText("Stop offline listening" if enabled else "Start offline listening")
        if enabled:
            self.start_listener(force=True)
        else:
            self.stop_listener()

    def schedule_listening(self):
        if not self.listener and self.background_listening and not self.busy and self.state != "speaking" and self.session.state != State.SLEEPING:
            QTimer.singleShot(800, self.background_capture)

    def start_listener(self, force=False):
        self.retired_listeners = [item for item in self.retired_listeners if item.thread and item.thread.is_alive()]
        if self.retired_listeners and not self.closing and self.settings.mic_enabled and not self.session.hard_muted:
            QTimer.singleShot(500, self.start_listener)
            return
        if self.closing or self.listener or self.retired_listeners or not self.settings.mic_enabled or self.session.hard_muted:
            return
        if not (self.settings.wake_word or force):
            return
        self.listener = LocalListener(self.settings, self.session)
        self.listener.heard.connect(self.local_utterance)
        self.listener.level.connect(self.audio_level)
        self.listener.status.connect(self.listener_status)
        self.listener.start()
        self.background_listening = True
        self.listen_button.setChecked(True)
        self.listen_button.setText("Stop offline listening")

    def stop_listener(self):
        if self.listener:
            self.listener.stop()
            if not self.listener.thread or not self.listener.thread.is_alive():
                self.listener.deleteLater()
            else:
                # Keep QObject/model alive until its cold-loading worker exits.
                self.retired_listeners.append(self.listener)
            self.listener = None

    def listener_status(self, text):
        if self.closing or (self.sender() is not None and self.sender() is not self.listener):
            return
        self.log(text)
        self.status.setText(("STANDBY · " if self.session.state == State.SLEEPING else "") + text)

    def local_utterance(self, generation, text, pcm):
        if self.sender() is not None and self.sender() is not self.listener:
            return
        if self.session.hard_muted or generation != self.session.generation:
            return
        command = control_phrase(text)
        if command == "wake":
            self.wake(from_voice=True)
            return
        if command == "sleep":
            self.sleep()
            return
        if self.session.state == State.SLEEPING or self.busy or self.state == "speaking":
            return
        if self.settings.recognition in {"cloud", "gemini"}:
            if self.settings.recognition == "gemini" and not gemini_key(self.vault):
                if text:
                    self.input.setPlainText(text)
                    self.send()
                else:
                    self.write("\nOffline speech could not recognize a command. Configure Gemini for multilingual cloud recognition.\n")
                return
            self.set_state("listening", "transcribing command")
            self.begin("listen", transcribe_pcm(self.settings, self.vault, pcm), "transcript")
        elif text:
            self.input.setPlainText(text)
            self.send()

    def wake(self, checked=False, from_voice=False):
        if not self.session.wake(from_voice=from_voice):
            return
        self.set_state("listening", "online and ready, ASH")
        self.write("\nJARVIS · Online and ready, ASH.\n")
        self.log("New awake session activated.")
        if not self.mute_button.isChecked():
            if not self.tts.availableVoices():
                self.voice_error("Local speech voices are unavailable. Install an OS speech voice and check the default output device; manual wake still works.")
                return
            self.set_state("speaking", "local wake acknowledgement")
            self.local_speaking = True
            self.tts.say("Online and ready, ASH.")
        self.start_listener()

    def sleep(self):
        self.session.sleep()
        self.pending_send = self.pending_speech = self.buffer = ""
        self.awaiting_wake_query = False
        self.microphone.stop()
        self.service.cancel()
        self.settings_panel.model_service.cancel()
        if self.approval_dialog:
            self.approval_dialog.reject()
        self.stop_speech()
        self.set_state("sleeping", "STANDBY · local wake detector only" if self.listener else "STANDBY · manual Wake")
        self.write("\nJARVIS · Entering standby mode, ASH.\n")
        self.log("Standby entered. Queued replies and actions invalidated; cancellation does not guarantee an API request was unbilled.")
        self.start_listener()

    def hard_mute(self, muted):
        self.session.mute(muted)
        self.settings.hard_mute = muted
        self.store.save_settings(self.settings)
        self.settings_panel.fields["hard_mute"].setChecked(muted)
        if muted:
            self.session.invalidate()
            self.pending_send = ""
            self.microphone.stop()
            self.service.cancel()
            self.settings_panel.model_service.cancel()
            if self.approval_dialog:
                self.approval_dialog.reject()
            self.stop_speech()
            self.stop_listener()
            self.listen_button.setChecked(False)
            self.listen_button.setText("Start offline listening")
            self.audio_level(0)
        else:
            self.start_listener()
        self.set_state(self.state, "MICROPHONE OFF" if muted else "microphone follows permissions")
        self.log("Hard mute enabled; no capture." if muted else "Hard mute disabled.")

    def background_capture(self):
        if not self.listener and self.background_listening and not self.busy and self.state != "speaking" and self.session.state != State.SLEEPING:
            self.start_capture()

    def configure_voice(self):
        self.tts.setRate(self.settings.voice_rate)
        self.tts.setVolume(self.settings.voice_volume)
        self.tts.voice = self.settings.local_voice
        for voice in self.tts.availableVoices():
            if voice.name() == self.settings.local_voice:
                self.tts.setVoice(voice)
        self.output.setVolume(self.settings.voice_volume)
        for device in QMediaDevices.audioOutputs():
            if bytes(device.id()).hex() == self.settings.speaker_device:
                self.output.setDevice(device)
        self.orb.timer.setInterval(250 if self.session.state == State.SLEEPING else 66 if self.settings.low_power else 33)

    def speak(self, text):
        if self.session.state == State.SLEEPING or not self.settings.speech_enabled or self.mute_button.isChecked() or self.busy:
            self.schedule_listening()
            return
        self.set_state("speaking", "spoken reply")
        if self.settings.speech_mode == "local":
            if not self.tts.availableVoices():
                self.voice_error("No local speech voice is available. Install an OS speech voice or configure cloud speech.")
                return
            self.local_speaking = True
            self.tts.say(text[:6000])
        else:
            self.begin("speech", synthesize(self.settings, self.vault, text), "speech_audio")

    def play_cloud(self, audio):
        directory = self.directory / "audio-cache"
        directory.mkdir(exist_ok=True)
        self.cleanup_audio()
        import uuid
        self.audio_file = directory / (uuid.uuid4().hex + ".wav")
        self.audio_file.write_bytes(audio)
        self.player.setSource(QUrl.fromLocalFile(str(self.audio_file)))
        self.set_state("speaking", "cloud speech playback")
        self.player.play()

    def tts_state(self, state):
        if state == QTextToSpeech.State.Speaking:
            self.set_state("speaking", "local native voice")
        elif state == QTextToSpeech.State.Ready and self.local_speaking:
            self.local_speaking = False
            self.session.capture_after = time.monotonic() + 0.6
            self.set_state("idle", "ready, ASH")
            self.schedule_listening()

    def player_state(self, state):
        if state == QMediaPlayer.PlaybackState.StoppedState:
            self.player.setSource(QUrl())
            self.cleanup_audio()
            if self.state == "speaking":
                self.set_state("idle", "ready, ASH")
                self.schedule_listening()

    def cleanup_audio(self):
        if self.audio_file:
            try:
                self.audio_file.unlink(missing_ok=True)
            except OSError:
                pass
            self.audio_file = None

    def voice_error(self, text):
        self.voice_error_count += 1
        self.set_state("error", text[:100])
        self.write("\n[Voice error] " + text + "\n")
        self.log("Voice output failed. Check selected device and voice in Settings.")

    def stop_speech(self):
        self.pending_speech = ""
        if self.busy and self.task_kind == "speech":
            self.session.invalidate()
            self.service.cancel()
        self.local_speaking = False
        self.session.capture_after = time.monotonic() + 0.6
        self.tts.stop()
        self.player.stop()
        self.player.setSource(QUrl())
        self.cleanup_audio()
        if self.state == "speaking":
            self.set_state("idle", "speech stopped")

    def stop_all(self):
        self.session.invalidate()
        self.background_listening = False
        self.listen_button.setChecked(False)
        self.listen_button.setText("Start offline listening")
        self.pending_send = ""
        self.microphone.stop()
        self.stop_listener()
        self.service.cancel()
        self.settings_panel.model_service.cancel()
        self.stop_speech()
        self.set_state("idle", "interrupted by ASH")
        self.log("Stop requested. Already completed Windows actions cannot be undone.")

    def apply_settings(self, settings):
        if self.busy:
            return
        try:
            self.stop_all()
            self.store.save_settings(settings)
            self.store.prune(settings.retention_days)
            self.settings = settings
            self.session.mute(settings.hard_mute)
            self.hard_mute_button.blockSignals(True)
            self.hard_mute_button.setChecked(settings.hard_mute)
            self.hard_mute_button.blockSignals(False)
            self.registry.platform.close()
            self.registry = Registry(settings, self.directory)
            self.engine = Engine(settings, self.vault, self.store, self.registry)
            self.configure_voice()
            self.setStyleSheet(STYLE.replace("#39dfff", "#639cff").replace("#36d7f4", "#639cff") if settings.theme == "blue" else STYLE)
            self.refresh_provider()
            self.refresh_history()
            self.start_listener()
            self.log("Settings saved. Local standby detection follows the approved microphone settings.")
            QMessageBox.information(self, "Settings saved", "Preferences are saved. Local standby detection starts only when microphone permission and the offline detector are enabled.")
        except Exception as exc:
            QMessageBox.warning(self, "Settings error", str(exc))

    def new_chat(self):
        if self.busy:
            return
        self.history, self.cid = [], None
        self.chat.clear()
        self.input.clear()
        self.write("JARVIS · Ready for a new conversation, ASH.\n")

    def refresh_history(self):
        self.history_list.clear()
        self.history_ids = []
        for cid, title in self.store.conversations():
            self.history_ids.append(cid)
            self.history_list.addItem(title)

    def load_history(self):
        row = self.history_list.currentRow()
        if self.busy or row < 0:
            return
        self.cid = self.history_ids[row]
        self.history = self.store.messages(self.cid)
        self.chat.clear()
        for message in self.history:
            self.write(("ASH" if message["role"] == "user" else "JARVIS") + " · " + message["content"] + "\n\n")
        self.show_page(0)

    def delete_history(self):
        row = self.history_list.currentRow()
        if self.busy or row < 0:
            return
        cid = self.history_ids[row]
        if QMessageBox.question(self, "Delete conversation", "Delete this saved conversation permanently?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.store.delete_conversation(cid)
            if self.cid == cid:
                self.new_chat()
            self.refresh_history()

    def refresh_memories(self):
        self.memory_list.clear()
        self.memory_ids = []
        for mid, text in self.store.memories():
            self.memory_ids.append(mid)
            self.memory_list.addItem(text)

    def add_memory(self):
        if self.busy:
            return
        text, ok = QInputDialog.getMultiLineText(self, "Save approved preference", "This preference will be stored locally and sent with future chat requests. Do not enter credentials.")
        if ok:
            try:
                self.store.save_memory(text)
                self.refresh_memories()
            except ValueError as exc:
                QMessageBox.warning(self, "Memory error", str(exc))

    def delete_memory(self):
        row = self.memory_list.currentRow()
        if not self.busy and row >= 0:
            self.store.delete_memory(self.memory_ids[row])
            self.refresh_memories()

    def refresh_commands(self):
        self.command_list.clear()
        self.commands = self.store.commands()
        for cid, label, tool, args in self.commands:
            self.command_list.addItem(label + " · " + tool)

    def add_command(self):
        if self.busy:
            return
        label, ok = QInputDialog.getText(self, "Custom command", "Display name")
        if not ok or not label.strip():
            return
        name, ok = QInputDialog.getItem(self, "Custom command", "Allowlisted tool", list(self.registry.tools), 0, False)
        if not ok:
            return
        args, ok = QInputDialog.getMultiLineText(self, "Validated arguments", "JSON object with exactly these keys: " + ", ".join(self.registry.tools[name].properties), "{}")
        if ok:
            try:
                parsed = json.loads(args)
                self.registry.tools[name].validate(parsed)
                self.store.save_command(label, name, parsed)
                self.refresh_commands()
            except Exception as exc:
                QMessageBox.warning(self, "Invalid command", str(exc))

    def run_command(self):
        row = self.command_list.currentRow()
        if row >= 0:
            _, label, name, args = self.commands[row]
            self.quick(name, json.loads(args))

    def delete_command(self):
        row = self.command_list.currentRow()
        if not self.busy and row >= 0:
            self.store.delete_command(self.commands[row][0])
            self.refresh_commands()

    def clear_data(self):
        if self.busy:
            return
        if QMessageBox.question(self, "Clear all JARVIS data", "Permanently delete conversations, memories, custom commands, settings, credentials and crash diagnostics? User-created files and screenshots remain in their chosen folders.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.stop_all()
        self.vault.clear()
        self.store.clear()
        import logging
        logger = logging.getLogger("jarvis")
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)
        for folder, pattern in [("audio-cache", "*.wav"), ("logs", "*.log*")]:
            for file in (self.directory / folder).glob(pattern):
                try:
                    file.unlink()
                except OSError:
                    pass
        self.settings = Settings()
        from .main import configure_logging
        configure_logging(self.directory)
        self.session.sleep()
        self.session.mute(self.settings.hard_mute)
        self.registry.platform.close()
        self.registry = Registry(self.settings, self.directory)
        self.engine = Engine(self.settings, self.vault, self.store, self.registry)
        old_panel = self.settings_panel
        old_panel.local_tts.close()
        old_panel.model_service.close()
        self.pages.removeWidget(old_panel)
        old_panel.deleteLater()
        self.settings_panel = SettingsPanel(self.settings, self.vault, self.directory)
        self.settings_panel.awake_guard = lambda: self.session.state != State.SLEEPING
        self.settings_panel.token_reader = lambda: self.session.generation
        self.settings_panel.model_service.validity = self.session.valid
        self.settings_panel.saved.connect(self.apply_settings)
        self.pages.insertWidget(3, self.settings_panel)
        self.configure_voice()
        self.new_chat()
        self.logs.clear()
        self.refresh_history()
        self.refresh_memories()
        self.refresh_commands()
        self.refresh_provider()
        self.show_page(0)

    def select_path(self, edit, directory):
        path = QFileDialog.getExistingDirectory(self, "Choose approved project") if directory else QFileDialog.getOpenFileName(self, "Choose approved source file")[0]
        if path:
            edit.setText(path)

    def ask_about_file(self):
        if self.busy:
            return
        if not self.settings.developer_mode:
            QMessageBox.information(self, "Developer mode", "Enable developer mode and approve your project folder in Settings first.")
            return
        self.input.setPlainText(self.code_task.currentText() + ". First use read_file to inspect this selected file: " + json.dumps(self.source_file.text()) + ". Do not modify files.")
        self.send()

    def export_diagnostics(self):
        path = QFileDialog.getSaveFileName(self, "Save sanitized diagnostics", "jarvis-diagnostics.txt", "Text files (*.txt)")[0]
        if path:
            try:
                Path(path).write_text(scrub(self.logs.toPlainText()), encoding="utf-8")
            except OSError as exc:
                QMessageBox.warning(self, "Export failed", str(exc))

    def closeEvent(self, event: QCloseEvent):
        if self.closing:
            if any(item.thread and item.thread.is_alive() for item in self.retired_listeners):
                event.ignore()
                QTimer.singleShot(500, self.close)
            else:
                event.accept()
            return
        self.closing = True
        self.metrics_timer.stop()
        self.flush_timer.stop()
        self.stop_all()
        self.tts.close()
        self.settings_panel.local_tts.close()
        for listener in self.retired_listeners:
            listener.stop()
        self.settings_panel.model_service.close()
        self.registry.platform.close()
        try:
            self.service.close()
        except Exception:
            pass
        if any(item.thread and item.thread.is_alive() for item in self.retired_listeners):
            self.status.setText("Closing local recognition safely; waiting for native model loading to finish…")
            self.setEnabled(False)
            event.ignore()
            QTimer.singleShot(500, self.close)
        else:
            event.accept()
