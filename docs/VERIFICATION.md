# Verification record — 11 October 2026

Development and tests ran on Windows 10 build 19045, Python 3.12.14, PySide6 6.8.3. This verifies the available Windows host, not performance on a separately identified i3-6100U / Intel HD 520 laptop.

## Verified

* Real native Qt window launch and app-owned window rendering, including provider settings.
* One second of actual Realtek microphone input: 44,100 captured frames at 44,100 Hz, nonzero signal. No microphone audio was saved or uploaded.
* Installed Windows SAPI voices: Microsoft Zira Desktop and Microsoft David Desktop. Local wake acknowledgement transitioned Speaking → Ready.
* Installed official small English Vosk model. Locally synthesized speech “Wake up Jarvis” transcribed to `wake up jarvis`, classified as wake. The model vocabulary includes `jarvis`.
* Windows DPAPI dummy-credential encryption/decryption and endpoint isolation. The sandbox cannot access the normal user's DPAPI profile; verification succeeded outside that sandbox using a dummy secret.
* SQLite settings/memory/history/custom command persistence, retention and deletion.
* Real system metrics/date/time and temporary file operations; approval denial and no-overwrite behavior.
* Mocked OpenAI-compatible and Anthropic streaming/tool calls/error handling, and native Gemini SDK data conversion with thought signatures and automatic execution disabled.
* Standby rejecting normal commands; repeated wake not duplicating sessions; hard mute preventing capture; sleep during approvals blocking writes; expired responses discarded; GUI heartbeat during asynchronous work; conversation resuming after wake.
* `pip check`: no broken requirements. Python source compilation succeeded.

## Not yet verified

No `GEMINI_API_KEY` is configured. Real Gemini model discovery, API chat, API tool-calling round trips, multilingual cloud transcription and free-tier account quota cannot be verified until ASH supplies a key in Settings or the environment. Alternate providers and cloud speech also require their own credentials.

The synthetic offline wake sample validates the recognizer pipeline, not ASH's real voice in a noisy room. Check all wake/sleep variations with the actual microphone after enabling local detection. Live microphone hot-plug recovery is covered by simulated disconnection tests but has not been physically exercised. Real shutdown/restart, screenshots of the user's desktop, volume changes and external browser/application launches were not triggered merely for automated verification.

Listening pauses while TTS plays to avoid self-triggering. Interrupt during playback with the UI controls. Voice sleep works while thinking and while listening; full-duplex echo-cancelled voice interruption is not implemented or claimed.

## Commands

The automated suite uses no real cloud requests and no destructive Windows actions:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q jarvis scripts tests
```

The normal user context is required for Windows DPAPI. Restricted automation sandboxes may also hide installed Windows voices/fonts. Native rendering and voice verification therefore ran in the normal Windows user context. Never skip an actual failure in a normal deployment merely to label the suite green.

The initial suite passed 44 tests but missed the real speech interruption crash. The recovery suite now passes **67 tests**. The packaged Windows executable launched successfully with exit code 0, local voices, bundled Vosk and system metrics, starting in SLEEPING with no microphone or API requests. The full record is in `BUILD-REPORT.md`.


Current recovery/package results supersede the initial checks above. See BUILD-REPORT.md and docs/CRASH-RECOVERY.md. Native Mac execution remains unverified.
