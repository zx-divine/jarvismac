# JARVIS recovery and cross-platform build report

11 October 2026. Executed on Windows 10 build 19045, Python 3.12.14, PySide6 6.8.3. This report supersedes the initial 44-test launch-only report.

## Crash cause and repairs

Windows Application events 1000/1001 at 22:05 identify a VCRUNTIME140.dll access violation (0xc0000005). Rapid wake acknowledgement followed by Sleep reproduced it twice, including with microphone capture disabled. The Qt SAPI speech interruption path was isolated as the trigger. The accessible Windows report had no symbolic minidump; an exact C++ instruction is not claimed. Local faulthandler traces and a pre-repair source backup are preserved in the ignored .recovery folder. See docs/CRASH-RECOVERY.md for reproducible steps and sanitized evidence.

Local TTS now runs in an interruptible native OS subprocess, with stdin-only speech text and receiver-bound Qt callbacks. A second reproduced callback-lifetime abort was repaired. Other fixes cover physical microphone abort/close, cancelled/obsolete recognition, mute/unmute generations, queued cloud speech interruption, cold-loading listener ownership, model caching, input-overflow handling, single-instance locking, native crash tracing, corrupt-state preservation and strict saved permission types. Gemini, other providers, memory, streaming, function calling, consent, developer tools and Windows automation remain intact.

## Executed Windows validation

| Check | Actual result |
| --- | --- |
| Automated suite | **67 passed, 0 failed, 0 skipped**, 11.97 seconds, normal Windows user context |
| Dependencies and compilation | pip check and Python compilation passed |
| Source native TTS | Speaking to Ready completed without reported speech error; installed David/Zira voices discovered |
| Original crash reproduction after repair | 20 manual wake/sleep/mute/stop steps with local microphone permission completed, exit 0; native trace empty |
| Physical microphone hardware | Actual Realtek input captured 44,100 frames at 44,100 Hz, RMS 0.006346; no audio saved/uploaded |
| Wake phrase transcription | Real Vosk model loaded; synthetic local phrase sample recognized in earlier verification; human microphone wake phrase **not verified** |
| State/voice safety | Tests cover sleeping startup, local speech controls, repeated wakes, expired replies/actions, Hard Mute across unmute, stopped cloud speech, simulated disconnect/invalid format, capture abort/close, missing model and UI lifecycle |
| Packaged executable | Final PyInstaller build completed; full package launched, four lifecycle cycles, zero reported voice errors, bundled Vosk loaded, sleeping finish, clean exit 0 |
| Clean exit and relaunch | Same isolated database reopened, instance lock released, bundled model loaded, zero voice errors, exit 0 |
| Key-free package | Microphone initially off, no AI task requested; local system metrics worked |
| Package measurements | UI first observed ready at **8.4 s**; full lifecycle/check exit **42.58 s** including the intentional 30 s hold and cold model check |
| Visible standby measurements | **105.2 MiB RSS**, **2.46% of one CPU core** mean across 14 one-second idle samples; model-loaded RSS **231.0 MiB** |
| Package size | 321,885,310 bytes, approximately 307 MiB; distribute the entire folder |

Executable: dist/JARVIS/JARVIS.exe. Launch using Start-JARVIS.bat. Tests, package/performance JSON, build logs and crash reproduction traces are local under .recovery and excluded from publishing. CPU/RAM observations describe this host, not a performance guarantee for another laptop. No shutdown/restart or unrelated personal file operation was executed during QA.

## macOS M1 implementation

Implemented shared Qt UI/providers/memory/voice state logic; platform adapters; native SecItem Keychain storage; cancellable say speech; macOS data paths; native volume/Music/Finder/TextEdit/System Settings actions; explicit Screen Recording checks; delayed abortable power requests; Vosk universal2 dependency; arm64 PyInstaller .app specification with privacy usage descriptions; setup/build scripts; Windows and macOS GitHub Actions.

Mac behavior was tested with dependency injection/mocks on Windows. No actual macOS device was connected. A native .app has **not** been built, signed with Developer ID, notarized, or tested on an M1 in this session. The Mac scripts refuse Windows/Rosetta, test and load real Vosk on the native host, then build and smoke-check an ad-hoc signed .app. CI execution status is recorded in the final handoff report. See docs/MACOS.md.

## Remaining acceptance and launch steps

Windows: double-click Start-JARVIS.bat, press Wake, then use local commands or Logs microphone/speaker tests. Enable microphone permission plus the offline detector in Settings for voice wake/sleep. With no Gemini key, local Vosk commands remain usable; arbitrary conversation gives setup guidance. Configure a key and discover a real model later for online AI.

Mac: obtain the prepared audited source archive, extract it on the M1, run bash scripts/setup_macos.sh, then .venv/bin/python -m jarvis. Build with bash scripts/build_macos.sh. Review normal macOS microphone/Automation/Screen Recording/Keychain permissions yourself.

Still unverified: the owner's actual spoken wake/sleep accuracy, unplug/reconnect with physical hardware, absent physical output hardware, real Gemini authentication/streaming/quota/function calls, and all native Mac hardware/permissions. Mocked provider tests do verify official SDK request serialization and error/cancellation boundaries. Speech remains half duplex; use Sleep, Stop Speaking or Hard Mute during playback. Audible playback was not independently confirmed by a human listener.

GitHub push pending — authentication required. The single noninteractive push failed with exit 128 and was not retried. No commit was pushed and GitHub Actions has not run for this local work.

Publishing: only safe source is authorized for https://github.com/zx-divine/jarvis on main. See docs/RELEASE-STATUS.md and the final handoff report for the actual commit and push outcome. No authenticator or interactive login is used.
