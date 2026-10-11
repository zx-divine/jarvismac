import dataclasses
from pathlib import Path
import sounddevice as sd
from PySide6.QtCore import Signal
from PySide6.QtMultimedia import QMediaDevices
from PySide6.QtTextToSpeech import QTextToSpeech
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QCheckBox, QSpinBox, QDoubleSpinBox, QPushButton, QListWidget, QListWidgetItem,
    QFileDialog, QLabel, QMessageBox, QTabWidget, QScrollArea, QHBoxLayout)
from PySide6.QtCore import Qt
from .config import Settings, ENDPOINTS
from .tools import Registry
from .worker import Service
from .speech import local_speech
from .security import gemini_key

class SettingsPanel(QWidget):
    saved = Signal(object)

    def __init__(self, settings, vault, private_dir):
        super().__init__()
        self.original, self.vault, self.private_dir = settings, vault, private_dir
        self.model_service = Service()
        self.model_service.event.connect(self.model_event)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)
        self.fields = {}
        def page(title):
            widget = QWidget()
            form = QFormLayout(widget)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(widget)
            tabs.addTab(scroll, title)
            return form
        def text(form, label, key, password=False):
            edit = QLineEdit(str(getattr(settings, key)))
            if password:
                edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.fields[key] = edit
            form.addRow(label, edit)
            return edit
        def combo(form, label, key, options):
            box = QComboBox()
            for label_text, value in options:
                box.addItem(label_text, value)
            box.setCurrentIndex(max(0, box.findData(getattr(settings, key))))
            self.fields[key] = box
            form.addRow(label, box)
            return box
        def check(form, label, key):
            box = QCheckBox(label)
            box.setChecked(getattr(settings, key))
            self.fields[key] = box
            form.addRow(box)
            return box
        def number(form, label, key, low, high, floating=False):
            spin = QDoubleSpinBox() if floating else QSpinBox()
            spin.setRange(low, high)
            if floating:
                spin.setSingleStep(0.1)
            spin.setValue(getattr(settings, key))
            self.fields[key] = spin
            form.addRow(label, spin)
        api = page("AI provider")
        provider = combo(api, "Provider", "provider", [("OpenAI", "openai"), ("Anthropic Claude", "anthropic"), ("Google Gemini", "gemini"), ("OpenAI compatible", "compatible")])
        text(api, "Model ID", "model").setPlaceholderText("Enter a model available to your API account")
        verify = QPushButton("Verify Gemini models with this API key")
        verify.clicked.connect(self.verify_models)
        api.addRow(verify)
        endpoint = text(api, "HTTPS API base URL", "endpoint")
        provider.currentIndexChanged.connect(lambda: endpoint.setText(ENDPOINTS[provider.currentData()]))
        self.chat_key = QLineEdit()
        self.chat_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.chat_key.setPlaceholderText("Leave blank to keep the saved endpoint-specific key")
        api.addRow("API key", self.chat_key)
        forget = QPushButton("Delete key for this provider / endpoint")
        forget.clicked.connect(lambda: self.delete_key("chat:" + provider.currentData(), endpoint.text()))
        api.addRow(forget)
        info = QLabel("Gemini uses the official google-genai SDK and GEMINI_API_KEY, with encrypted Settings credentials as a fallback. Verify models before selecting one.\nFree tiers have account-specific request/token/daily limits. Model discovery does not prove free-tier eligibility. Check AI Studio and Google's current pricing. This app never enables paid billing.\nChat subscriptions (including Claude Code) do not supply API credits. Other providers remain available. Keys saved here are encrypted with Windows DPAPI.")
        info.setWordWrap(True)
        api.addRow(info)
        number(api, "Context budget (characters)", "context_chars", 4000, 100000)

        voice = page("Voice & privacy")
        check(voice, "Allow microphone capture", "mic_enabled")
        check(voice, "Hard mute microphone (no capture, no voice wake)", "hard_mute")
        combo(voice, "Recognition", "recognition", [("Gemini speech input (uploads speech only while awake)", "gemini"), ("OpenAI-compatible audio API (uploads speech)", "cloud"), ("Offline Vosk", "vosk")])
        mic = combo(voice, "Microphone", "mic_device", [("Windows default input", None)])
        try:
            for index, device in enumerate(sd.query_devices()):
                if device["max_input_channels"] > 0:
                    mic.addItem(f"{index}: {device['name']}", index)
            mic.setCurrentIndex(max(0, mic.findData(settings.mic_device)))
        except Exception:
            voice.addRow(QLabel("No audio device detected. Reconnect it and reopen Settings."))
        model_row = QWidget()
        model_layout = QHBoxLayout(model_row)
        model_layout.setContentsMargins(0, 0, 0, 0)
        vosk = QLineEdit(settings.vosk_model)
        self.fields["vosk_model"] = vosk
        model_layout.addWidget(vosk)
        browse = QPushButton("Browse")
        browse.clicked.connect(lambda: self.choose_folder(vosk))
        model_layout.addWidget(browse)
        voice.addRow("Offline model folder", model_row)
        check(voice, "Continuous offline listening (start manually each session)", "continuous")
        check(voice, "Enable offline standby wake/sleep detector (starts after permission is saved)", "wake_word")
        number(voice, "Voice activity threshold (lower is more sensitive)", "vad_threshold", 0.001, 0.2, True)
        self.fields["vad_threshold"].setDecimals(3)
        self.fields["vad_threshold"].setSingleStep(0.001)
        self.fields["vad_threshold"].setValue(settings.vad_threshold)
        combo(voice, "Language", "language", [("Auto / Hinglish", "auto"), ("English", "en"), ("Hindi", "hi")])
        check(voice, "Speak replies", "speech_enabled")
        combo(voice, "Speech output", "speech_mode", [("Local OS voice (offline)", "local"), ("Cloud audio API (uploads reply text)", "cloud")])
        local_voice = combo(voice, "Local voice", "local_voice", [("System default", "")])
        tts = local_speech(self)
        for available in tts.availableVoices():
            local_voice.addItem(available.name(), available.name())
        local_voice.setCurrentIndex(max(0, local_voice.findData(settings.local_voice)))
        def refresh_voices():
            selected = local_voice.currentData() or settings.local_voice
            local_voice.clear()
            local_voice.addItem("System default", "")
            for available in tts.availableVoices():
                if available.name() != "System default":
                    local_voice.addItem(available.name(), available.name())
            local_voice.setCurrentIndex(max(0, local_voice.findData(selected)))
        tts.voicesChanged.connect(refresh_voices)
        self.local_tts = tts
        outputs = [("System default speaker", "")]
        outputs += [(d.description(), bytes(d.id()).hex()) for d in QMediaDevices.audioOutputs()]
        combo(voice, "Cloud speech speaker", "speaker_device", outputs)
        note = QLabel("Local speech uses the OS default output device. Change it in your system Sound settings.\nVosk accuracy and languages depend on the downloaded model. An English model is required for the listed English wake/sleep phrases. Cloud recognition can transcribe multilingual commands while awake.\nWake/sleep always stays local. Listening is paused during TTS to prevent self-triggering; use Stop Speaking or Sleep buttons to interrupt playback.")
        note.setWordWrap(True)
        voice.addRow(note)
        number(voice, "Voice speed (−1 to +1)", "voice_rate", -1, 1, True)
        number(voice, "Voice volume (0 to 1)", "voice_volume", 0, 1, True)
        text(voice, "Audio HTTPS API base URL", "audio_endpoint")
        text(voice, "Transcription model", "transcription_model")
        text(voice, "Cloud speech model", "speech_model")
        text(voice, "Cloud voice ID", "speech_voice")
        self.audio_key = QLineEdit()
        self.audio_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.audio_key.setPlaceholderText("Separate audio credential; blank preserves saved key")
        voice.addRow("Audio API key", self.audio_key)
        forget_audio = QPushButton("Delete audio key for this endpoint")
        forget_audio.clicked.connect(lambda: self.delete_key("audio", self.fields["audio_endpoint"].text()))
        voice.addRow(forget_audio)
        disclosure = QLabel("Microphone is off by default. No recording starts at launch. Cloud transcription sends only a bounded push-to-talk recording containing detected speech. Audio is held in memory. Local TTS sends no text or audio to the cloud. Cloud TTS sends reply text. Stop/interrupt cancels pending requests and playback.")
        disclosure.setWordWrap(True)
        voice.addRow(disclosure)

        privacy = page("Files & actions")
        privacy.addRow(QLabel("Only the folders listed below are accessible to file tools."))
        self.folders = QListWidget()
        self.folders.addItems(settings.approved_folders)
        self.folders.setMinimumHeight(120)
        privacy.addRow("Approved folders", self.folders)
        add_folder = QPushButton("Approve a folder…")
        add_folder.clicked.connect(self.add_folder)
        remove_folder = QPushButton("Remove selected folder")
        remove_folder.clicked.connect(lambda: self.folders.takeItem(self.folders.currentRow()) if self.folders.currentRow() >= 0 else None)
        privacy.addRow(add_folder)
        privacy.addRow(remove_folder)
        check(privacy, "Enable developer tools (commands still require approval)", "developer_mode")
        self.permissions = QListWidget()
        all_settings = dataclasses.replace(settings, developer_mode=True)
        for tool in Registry(all_settings, private_dir).tools.values():
            item = QListWidgetItem(tool.name + " — " + tool.description)
            item.setData(Qt.ItemDataRole.UserRole, tool.name)
            item.setCheckState(Qt.CheckState.Unchecked if tool.name in settings.disabled_tools else Qt.CheckState.Checked)
            self.permissions.addItem(item)
        self.permissions.setMinimumHeight(240)
        privacy.addRow("Enabled tools", self.permissions)
        privacy.addRow(QLabel("Every enabled action still asks for approval. System metrics are read-only and do not prompt."))

        memory = page("Memory & appearance")
        check(memory, "Save future conversation text locally (opt-in)", "remember_history")
        number(memory, "Conversation retention (days)", "retention_days", 1, 3650)
        check(memory, "Low power animation (15 FPS)", "low_power")
        combo(memory, "Accent theme", "theme", [("Arc cyan", "cyan"), ("Electric blue", "blue")])
        check(memory, "Start minimized when launched", "start_minimized")
        notice = QLabel("No automatic startup task is installed. To launch at sign-in, place a shortcut to Start-JARVIS.bat in your Windows Startup folder.\nHistory and approved memories are local plaintext SQLite data. Do not save credentials or sensitive information there. Memories are sent to your chosen AI provider with chat requests.")
        notice.setWordWrap(True)
        memory.addRow(notice)
        save = QPushButton("Save settings securely")
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        layout.addWidget(save)

    def choose_folder(self, edit):
        path = QFileDialog.getExistingDirectory(self, "Choose extracted offline model")
        if path:
            edit.setText(path)

    def add_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Approve directory for JARVIS tools")
        if path and not self.folders.findItems(path, Qt.MatchFlag.MatchExactly):
            self.folders.addItem(path)

    def delete_key(self, purpose, endpoint):
        try:
            self.vault.delete(purpose, endpoint.rstrip("/"))
            QMessageBox.information(self, "Credential deleted", "The selected endpoint's saved key was removed.")
        except Exception as exc:
            QMessageBox.warning(self, "Credential error", str(exc))

    def save(self):
        try:
            data = self.original.to_dict()
            for key, widget in self.fields.items():
                if isinstance(widget, QLineEdit):
                    data[key] = widget.text().strip()
                elif isinstance(widget, QComboBox):
                    data[key] = widget.currentData()
                elif isinstance(widget, QCheckBox):
                    data[key] = widget.isChecked()
                else:
                    data[key] = widget.value()
            data["approved_folders"] = [self.folders.item(i).text() for i in range(self.folders.count())]
            data["disabled_tools"] = [self.permissions.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.permissions.count()) if self.permissions.item(i).checkState() != Qt.CheckState.Checked]
            result = Settings(**data)
            result.validate()
            if (result.mic_enabled and result.recognition in {"cloud", "gemini"} and (not self.original.mic_enabled or self.original.recognition != result.recognition or result.audio_endpoint != self.original.audio_endpoint)) or (result.speech_enabled and result.speech_mode == "cloud" and (not self.original.speech_enabled or self.original.speech_mode != "cloud" or result.audio_endpoint != self.original.audio_endpoint)):
                destination = ENDPOINTS["gemini"] if result.recognition == "gemini" else result.audio_endpoint
                answer = QMessageBox.question(self, "Cloud speech disclosure", "While awake, cloud recognition uploads recorded microphone speech. Standby wake/sleep stays local. Cloud synthesis uploads assistant reply text.\n\nRecognition destination: " + destination + "\nCloud speech output destination: " + result.audio_endpoint + "\n\nEnable the selected cloud voice features?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:
                    return
            if result.wake_word and result.mic_enabled and not result.hard_mute and (not self.original.wake_word or not self.original.mic_enabled):
                if QMessageBox.question(self, "Local standby microphone", "Enable local microphone listening while JARVIS is sleeping? Standby audio is never sent to cloud services. Hard Mute stops capture completely.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                    return
            if self.chat_key.text().strip():
                self.vault.set("chat:" + result.provider, result.endpoint, self.chat_key.text().strip())
            if self.audio_key.text().strip():
                self.vault.set("audio", result.audio_endpoint, self.audio_key.text().strip())
            self.chat_key.clear()
            self.audio_key.clear()
            self.saved.emit(result)
            self.original = result
        except Exception as exc:
            QMessageBox.warning(self, "Settings could not be saved", str(exc))

    def verify_models(self):
        if hasattr(self, "awake_guard") and not self.awake_guard():
            QMessageBox.information(self, "Wake JARVIS first", "Wake JARVIS before verifying Gemini models. Standby makes no API requests.")
            return
        key = self.chat_key.text().strip() or gemini_key(self.vault)
        token = self.token_reader() if hasattr(self, "token_reader") else 0
        async def verify():
            from .gemini import discover_models
            return await discover_models(key)
        self.model_service.submit(verify(), "models", token)

    def model_event(self, generation, kind, result):
        if not self.model_service.validity(generation):
            return
        if kind == "models":
            from PySide6.QtWidgets import QInputDialog
            if not result:
                QMessageBox.warning(self, "No models", "No compatible Gemini text models were returned for this API key.")
                return
            # Recommended only when returned by this account's actual model listing.
            recommended = "gemini-3.8-flash"
            index = result.index(recommended) if recommended in result else 0
            model, ok = QInputDialog.getItem(self, "Verified Gemini models", "Available to this API key. Confirm free-tier pricing/quota in AI Studio before use.", result, index, False)
            if ok:
                self.fields["provider"].setCurrentIndex(self.fields["provider"].findData("gemini"))
                self.fields["model"].setText(model)
        elif kind == "failed":
            QMessageBox.warning(self, "Model verification failed", result)
