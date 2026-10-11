# JARVIS build and test report

11 October 2026 — Windows 10 build 19045, Python 3.12.14, PySide6 6.8.3.

* **44 automated tests passed** in the normal Windows user context. Includes storage, DPAPI encryption, validated PC tools, approvals, streaming/provider errors, real Google SDK serialization/model-discovery against mock transport, wake/sleep generations, hard mute, queued voice suppression, simulated microphone disconnection, and responsive GUI checks.
* `pip check` passed; Python compilation passed.
* Native Windows source application launched and rendered. Local SAPI wake acknowledgement transitioned Speaking → Ready; installed voices included Microsoft Zira Desktop and Microsoft David Desktop.
* Actual Realtek microphone captured one second: 44,100 frames at 44,100 Hz. The microphone audio was not saved or uploaded.
* Official small English Vosk model downloaded, loaded, and recognized a locally generated “Wake up Jarvis” sample. `jarvis` exists in the model vocabulary.
* PyInstaller produced `dist/JARVIS/JARVIS.exe` with Qt libraries, provider SDKs and the Vosk model. Distribute the entire `dist/JARVIS` directory (approximately 307 MiB), not only the executable.
* **Final packaged native launch check passed (exit code 0)** after the hard-mute fix: SLEEPING, local voices available, bundled Vosk loaded, system metrics available, no microphone capture, no API requests. The final check took 24.9 seconds including offline-model loading and used 229.2 MiB of resident memory; the preceding optimized check took 14.5 seconds. These are smoke-check observations on the available host, not target-laptop performance guarantees.

The launcher `Start-JARVIS.bat` prefers the packaged executable. Complete source and setup/build/test scripts are also included.

## Required owner setup / remaining acceptance checks

There is no Gemini API key configured. Set `GEMINI_API_KEY` or save the key in Settings, verify the account's available models, select a current free-tier model, and confirm AI Studio quota/pricing. Real Gemini chat/tool round trips and multilingual cloud speech remain unverified until then. The app does not enable paid billing.

Enable microphone permission and the local wake detector to use voice activation. Test the listed phrases with ASH's actual voice and room acoustics. Only one-second capture and a synthetic offline speech sample have been hardware/pipeline checked; acoustic accuracy is not claimed.

Speech is half duplex: local listening pauses during TTS. Use Sleep, Stop Speaking or Hard Mute to interrupt playback. Voice sleep remains available while listening or thinking. No full-duplex acoustic echo cancellation is claimed.

External application/browser launches, desktop screenshots, system volume changes and shutdown/restart were not triggered just to manufacture acceptance evidence. Temporary file operations, actual metrics/time and approval boundaries were tested. Physically unplugging/reconnecting audio hardware remains a manual check.

The original and additive specifications are preserved verbatim in `docs/`. Detailed configuration, security boundaries, provider requirements, recovery and packaging instructions are in `README.md` and `docs/VERIFICATION.md`.
