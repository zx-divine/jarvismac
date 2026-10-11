# J.A.R.V.I.S. — ASH's personal desktop assistant

A real Windows/Python/PySide6 desktop application with Gemini as its primary AI brain, permission-controlled PC tools, local wake/sleep recognition, and optional conversation memory. OpenAI-compatible and Anthropic providers are retained. No Docker, WSL, local LLM, web server, or GPU renderer is required.

## Start on this computer

Double-click **Start-JARVIS.bat**. It uses the packaged `dist/JARVIS/JARVIS.exe` when available, otherwise the project's virtual environment. The environment and small English Vosk model have been installed during development.

JARVIS starts in **STANDBY**. The first installation does not capture audio until you explicitly enable microphone access. Press **Wake JARVIS** for text interaction and local commands.

1. Open **Settings → AI provider**. Gemini is selected by default.
2. Enter your Gemini API key and click **Verify Gemini models with this API key** while awake. Alternatively launch with the `GEMINI_API_KEY` environment variable. Select a model actually returned for your account; then save Settings.
3. Confirm the model's free-tier eligibility and your quota in [Google AI Studio](https://aistudio.google.com/) and [Google's pricing page](https://ai.google.dev/gemini-api/docs/pricing). Listing models verifies availability, not billing tier. No code enables paid billing or changes your Google project.
4. Send a message. Missing/invalid keys, unavailable models, quota errors and network failures produce setup guidance. Nothing simulates an AI reply.
5. For voice wake/sleep, open **Voice & privacy**, enable microphone permission and the **offline standby wake/sleep detector**, and select the installed `models/vosk-model-small-en-us-0.15` folder. Confirm the local-listening disclosure. The detector starts after these settings are saved and at subsequent launches where permission remains enabled.
6. For multilingual voice commands, select **Gemini speech input**. It uses your Gemini key and selected audio-capable model while awake. Use **Local Windows voice** for speech output without a second API key. Enable **Speak replies** if desired. Offline Vosk and an OpenAI-compatible audio API are also available.
7. Approve only the project directories you want accessible under **Files & actions**. All file-content transfers and PC actions ask before running. Developer commands additionally require developer mode.

**Do not paste credentials into chat or saved memories.** Enter keys in Settings, which protects them with Windows DPAPI, or use an environment variable. Environment keys take precedence for Gemini. `.env` is ignored by Git and is deliberately not automatically loaded; `.env.example` documents the variable without a secret.

## Setup on another Windows computer

Windows 10 64-bit, Python 3.11 or 3.12 from [python.org](https://www.python.org/downloads/windows/), and internet access for installation are sufficient. Include the Python launcher when installing Python.

Run `Setup-JARVIS.bat`, then `Start-JARVIS.bat`. Setup installs the locked environment and downloads the small official offline English model. For Python 3.12 instead of 3.11:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\download_voice_model.py
.\.venv\Scripts\python.exe -m jarvis
```

`requirements.txt` pins direct runtime dependencies. `requirements-lock.txt` captures the complete Windows development environment, including test/build dependencies. To reproduce that exact environment use `pip install -r requirements-lock.txt`. Do not copy a virtual environment between computers; recreate it. A packaged build needs no installed Python.

API credentials are private to the current Windows user/computer profile. Migrating encrypted blobs to another account is unsupported: enter the key again. The app does not obtain API access from a Claude Code or other chat subscription.

## Wake, sleep and hard mute

| State/control | Behavior |
| --- | --- |
| SLEEPING / STANDBY | No normal conversation, AI requests, cloud transcription, or tool dispatch. Only the approved local detector remains active. |
| LISTENING | Accept text and voice requests. Microphone waveform reflects input level. |
| THINKING / PROCESSING | Run cancellable AI/local tasks off the UI thread. The local detector can still recognize sleep. |
| SPEAKING | Play the selected voice. Listening pauses during playback and briefly afterward to prevent self-triggering. |
| Hard Mute | Stop every microphone stream, including wake detection. Manual Wake and text chat still work. Unmute manually to restore permitted capture. |
| Stop Speaking | Interrupt playback. Sleep also interrupts playback and invalidates all queued replies/actions. |
| Stop all | Cancel the active session's work and stop background listening. Already started Windows operations cannot be undone. |

Local phrases: **Wake up, Jarvis**, **Hey Jarvis, wake up**, **Jarvis, activate**, **Jarvis, online**, and the original **Hey Jarvis**. Sleep phrases: **Jarvis, go to sleep**, **Jarvis, sleep**, **Jarvis, standby**, **Jarvis, go offline**, **Go to sleep, Jarvis**. These controls also work as typed commands without any API call.

Wake acknowledgements use local Windows SAPI speech so they work offline. Recognition requires a real installed Vosk model. The supplied English model contains the word `jarvis`; recognition accuracy still depends on ASH's voice, microphone and room noise. It is phrase recognition, not a custom commercial wake-word detector. The VAD threshold can be adjusted; lower values accept quieter input but more noise. There is no claimed calibrated wake-word sensitivity score.

Speech is half duplex. Use **Stop Speaking**, **Sleep**, or **Hard Mute** to interrupt during playback; voice sleep recognition resumes after playback. This prevents the assistant's own voice from issuing commands without pretending to implement acoustic echo cancellation. During thinking, voice sleep remains available through the independent local detector.

Normal commands while sleeping are ignored. Every wake creates a generation identifier; repeated wakes do not duplicate sessions. Sleep invalidates that identifier before cancelling tasks. Provider responses, transcription results, TTS buffers, deferred callbacks and approvals from an older generation are discarded. A Windows action that already started may complete, and cancelling a cloud request does not guarantee it was not billed.

Continuous listening is disabled by default. Wake listening also requires explicit microphone permission. You can stop background detection entirely with **Stop offline listening**, **Stop all**, Hard Mute, or by disabling it in Settings. The window may be minimized while detection runs. Closing the window stops the app; no hidden service or remote-control port is installed.

## AI, languages and cost

Gemini uses the official **google-genai** Python SDK, manual function calling, streaming, bounded context, timeouts and bounded retries. SDK automatic function execution is disabled. Opaque Gemini thought signatures and function identifiers are retained in the active tool round trip; they are not displayed or saved in history.

Google's documentation checked on **11 October 2026** lists a free tier for `gemini-3.8-flash`. The Settings verifier recommends it only if the account's actual model listing returns it. There is no hardcoded default model; choose an available model and verify current pricing. Quotas depend on project/tier and include requests per minute, tokens per minute and daily limits. Check [current rate limits](https://ai.google.dev/gemini-api/docs/rate-limits); no fixed quota is promised. Free-tier content may be used by Google to improve its products, as disclosed on its pricing page. Avoid sensitive prompts if that policy is unsuitable.

Gemini chat and audio input can handle English, Hindi and Hinglish. The small offline English Vosk model does not provide reliable Hindi/Hinglish transcription. Gemini audio input is the default multilingual option while awake. Both transcription and subsequent chat consume requests; silence makes no cloud request. Windows Hindi TTS requires an installed Hindi Windows voice, or a suitable cloud voice.

Alternative chat providers remain selectable:

* OpenAI / compatible: HTTPS Chat Completions streaming with function calling. Configure a tool-capable model and endpoint-specific key.
* Anthropic: native Messages streaming with tool use and an Anthropic API key.
* OpenAI-compatible speech: separate audio API key, transcription model, TTS model and voice. Microphone audio / reply text goes to that configured endpoint only when the selected cloud feature is active.

Local speech uses the Windows default speaker and installed Windows voices. Cloud speech supports speaker selection in Settings. Change the local SAPI output through Windows Sound settings. Device enumeration is refreshed by reopening the app; the background detector retries a disconnected input locally without cloud traffic.

## Windows tools and developer mode

Real tools include CPU/RAM/disk/battery metrics, current date/time, VS Code/Chrome/Edge/Notepad/Calculator/Explorer/Settings launch, HTTPS websites, browser web search, bounded filename searches, selected UTF-8 source reads, new folders and text/source files, approved projects, volume/media keys, explicitly approved PNG screenshots, and confirmed shutdown/restart with a 60-second abort window.

The registry validates exact JSON keys/types and rejects unknown tools. Every action and file read/search asks for approval; read-only system/time metrics do not. Launch results accurately report a request sent to Windows, rather than claiming the application/page is ready. Screenshots stay in the chosen approved folder and are not uploaded. Browser search opens a search page; JARVIS does not pretend to have read its results.

Developer mode supports selected-code explanation, debugging, security review and patch suggestions through real AI. It never modifies existing source. Approved command presets are `git status`, `git diff`, `python -m pytest -q`, and `npm test -- --watch=false`; output and exit code are shown, with a 60-second timeout and 64 KB output cap. Process trees are terminated on cancellation. Presets execute trusted project code and are **not** an OS sandbox. Review the directory before approval. Packaged JARVIS cannot serve as a Python interpreter; run pytest using the source environment or your terminal.

Custom commands save a tool name and validated JSON arguments, not arbitrary shell text. File access is limited to explicitly approved local folders. Credential paths, alternate data streams, device/network paths, symbolic links, junctions and JARVIS private storage are blocked. New file creation uses exclusive mode and never overwrites. There is no file-deletion or arbitrary-shell tool.

## Memory, privacy and diagnostics

Settings, approved folders, custom commands, approved memories and opt-in chat history use SQLite under `%LOCALAPPDATA%\ASH-JARVIS`. `JARVIS_DATA_DIR` can override that location for development. In-session conversational context works even when transcript storage is disabled. Sleep preserves the current conversation for follow-up questions after waking.

History is off by default; enable it explicitly to save future text. Retention defaults to 30 days and is applied at startup and settings changes. You can delete individual conversations, delete memories, or clear all app data/credentials in **Memory & security**. Memories are sent with future chat requests. SQLite is plaintext, so only save information you approve. Clear Data does not remove environment variables managed by Windows or user-created files/screenshots outside the app's private data directory.

Audio capture stays in memory. Cloud TTS uses a transient local WAV for playback, removed afterward and cleaned after a crash. No microphone recordings are saved by default. Diagnostics contain session action names/status and sanitized crash stack locations, not conversation text, API bodies, credentials or tool arguments. Exported diagnostic copies belong to you and are not removed by Clear Data.

Files and command output are marked as untrusted data, known secret patterns are redacted, and the system prompt instructs providers to ignore embedded instructions. Model instructions alone cannot guarantee immunity to prompt injection: the enforceable boundary is validated capabilities and ASH's approval for all sensitive actions. Do not approve an unexpected action merely because the model requested it. No downloaded program or model response is automatically executed.

## Tests and packaging

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\Package-JARVIS.bat
```

The build is `dist\JARVIS\JARVIS.exe`. Distribute the entire `dist\JARVIS` directory, including `_internal`, Qt plugins and the Vosk model. The launcher prefers this build. Packaging uses PyInstaller in directory mode for more predictable startup and dependency loading. Build on Windows; this is not a signed installer or a security audit certification. PySide6 and bundled dependencies retain their upstream licenses; review distribution/license obligations before publishing.

For a deliberate microphone capture check run `scripts/check_microphone.py` (one second, no save/upload). `scripts/smoke_desktop.py --voice --native` opens the actual window briefly and exercises local speech. The test suite uses mocked cloud responses and dummy credentials; it does not spend API credits. See [verification details](docs/VERIFICATION.md) for actual checks and remaining acceptance work.

## Troubleshooting

* **No Gemini key/model:** Wake manually, configure the key, verify models, select one, save. Never share the key in chat.
* **HTTP 429:** Check project quota in AI Studio. Retry later or choose an available free-tier model; the app does not enable billing.
* **No microphone / disconnect:** Windows Settings → Privacy → Microphone must allow desktop apps. Select an input device and remove Hard Mute. The local detector retries hardware errors.
* **Wake unavailable:** Confirm the Vosk folder contains `am`, use an English model with `jarvis` in its vocabulary, and enable local detection. Manual Wake always remains available.
* **No spoken reply:** Choose an installed Windows SAPI voice, enable Speak replies and unmute replies. Wake acknowledges locally even when normal spoken replies are disabled. Cloud output needs its separate audio credential.
* **Files blocked:** Approve the specific project folder. Links/junctions and credential paths remain blocked even under an approved root.
* **Startup settings/database failure:** Close JARVIS, back up `%LOCALAPPDATA%\ASH-JARVIS`, and rename `jarvis.sqlite3` plus its `-wal`/`-shm` companions to recover with fresh settings. Re-enter credentials if DPAPI fails after a Windows profile migration. Never delete personal project folders during recovery.
* **Automatic startup:** Create your own shortcut to Start-JARVIS.bat in the Windows Startup folder. JARVIS installs no startup task. Start-minimized is selectable in Settings.

## Source map

`ui.py` and `orb.py`: native Qt interface and lightweight painter animation. `session.py`: thread-safe state/generation gate. `worker.py`: asyncio service thread and approval futures. `listener.py` / `audio.py` / `speech.py`: local detection, capture/VAD, cloud transcription and speech. `gemini.py` / `providers.py`: cloud adapters. `tools.py` / `security.py`: validated PC capabilities, filesystem policy and DPAPI. `storage.py` / `config.py`: SQLite and persistent settings. `tests/`: safety, streaming, storage, concurrency and GUI checks.

The original specification and additive update are preserved verbatim in [original requirements](docs/ORIGINAL-REQUIREMENTS.md) and [Gemini/wake-sleep requirements](docs/GEMINI-WAKE-SLEEP-REQUIREMENTS.md).
