# J.A.R.V.I.S. for Apple Silicon macOS

Native Python/PySide6 desktop assistant for M1 and other Apple Silicon Macs. Gemini is the primary AI provider; optional OpenAI-compatible and Anthropic providers remain available. This repository contains Mac launchers, Mac dependencies and a native arm64 build workflow.

## Install and launch

Use macOS 12 or newer with native arm64 Python 3.12. Open a native Terminal (not Rosetta), then:

```bash
git clone https://github.com/zx-divine/jarvismac.git
cd jarvismac
bash scripts/setup_macos.sh
.venv/bin/python -m jarvis
```

Finder launchers are `Setup-JARVIS.command`, `Start-JARVIS.command` and `Package-JARVIS.command`. Setup installs the Mac dependencies and downloads the local English Vosk model. Start opens `dist/JARVIS.app` if built, otherwise starts the source environment. Do not transfer a Windows virtual environment or executable to the Mac.

## Gemini and voice

JARVIS starts in standby. Wake manually, open Settings, enter a Gemini API key, verify the models available to your account and select one. An existing `GEMINI_API_KEY` environment variable takes precedence; `.env` files are not loaded automatically. Keys entered in Settings use native macOS Keychain. Never put keys into chat, source or Git.

Gemini uses the official google-genai SDK with streaming, bounded conversation context, timeouts, bounded retries and manual function calling. Automatic SDK function execution is disabled. Alternative chat providers and separate cloud audio credentials remain supported. Check current model pricing and quota in your provider account; JARVIS does not enable billing.

Local wake/sleep requires explicit microphone permission and enabling the offline standby detector in Settings. Select the installed Vosk model and input device. Wake phrases include “Wake up, Jarvis” and “Hey Jarvis”; sleep phrases include “Jarvis, go to sleep” and “Jarvis, standby”. Typed wake/sleep commands also work without API calls. The small English model is not reliable for Hindi/Hinglish; Gemini speech input is available while awake with a suitable model and key.

Local speech uses macOS `/usr/bin/say` and installed voices. Listening pauses during speech. Stop Speaking, Sleep or Hard Mute interrupts playback. Hard Mute closes every microphone stream and invalidates queued recognition; restore microphone capture manually. Sleep blocks normal AI requests and tool dispatch and discards stale replies/actions. No hidden service is installed; closing the window stops the app.

## Mac tools, permissions and privacy

Allowlisted tools include Finder, TextEdit, System Settings, Calculator, browser/VS Code launches, Music controls, volume, system metrics, date/time, approved screenshots and confirmed power actions with a cancellation window. File access is limited to approved folders. Sensitive actions, file searches/reads and content transfers require approval; no arbitrary shell or deletion tool exists. Developer command presets remain permission-controlled.

Grant Microphone, Automation or Screen Recording permissions only when needed through normal macOS controls. Do not grant blanket Accessibility or Full Disk Access for this app. See [Mac permissions and build instructions](docs/MACOS.md).

Settings and opt-in SQLite history/memory live under `~/Library/Application Support/ASH-JARVIS`. History is off by default; session context works without saving transcripts. Approved memories are sent with future chat requests. SQLite is plaintext, so save only approved information. Credential material is stored in Keychain rather than the database. Microphone recordings are not saved by default; cloud audio is sent only for enabled cloud features. Diagnostics omit credentials and conversation contents.

## Tests and native application build

```bash
bash scripts/build_macos.sh
open dist/JARVIS.app
```

The Mac build checks arm64 Python, installs Mac development requirements, runs tests, loads the actual Vosk library/model, builds the arm64 `.app`, verifies its ad-hoc signature, performs a package startup smoke check and creates `dist/JARVIS-macos-arm64.zip`. Generated packages are excluded from Git. No local Windows rebuild is involved.

[GitHub Actions](https://github.com/zx-divine/jarvismac/actions) runs only the Mac job for this repository and uploads the `JARVIS-macos-arm64` artifact. The original shared-source Mac job passed and produced an artifact; the corrected layout needs its own CI verification. See [verification record](docs/VERIFICATION.md).

Ad-hoc signing is not Developer ID signing or notarization. Native CI does not verify your M1 microphone, room accuracy, permissions or live automation. Follow normal macOS security controls and the hardware acceptance checklist in [docs/MACOS.md](docs/MACOS.md).

## Source structure

`jarvis/` retains the working shared engine, Qt UI, providers, voice, memory, security and platform adapters. Runtime platform guards select Mac Keychain, speech and automation paths on macOS. Cross-platform internals and regression tests are retained to preserve features; there are no Windows batch launchers or Windows environment lockfiles in this repository's current tree.

The Windows project is maintained separately at https://github.com/zx-divine/jarvis.
