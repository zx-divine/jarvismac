# Apple Silicon handoff

One shared source tree runs the Qt GUI, Gemini/other providers, SQLite memory, streaming, approvals, developer mode and local wake/sleep generation gate. The macOS adapter maps Explorer/Notepad/Windows Settings aliases to Finder/TextEdit/System Settings. It uses fixed native `open`/AppleScript commands, never an arbitrary shell. Mac media controls target an already-running Music app. Screenshots require explicit tool approval and existing OS Screen Recording permission. Power requests have a real 60-second app-owned abort window and are cancelled when JARVIS closes or replaces its adapter.

Credentials use native Security framework SecItem generic-password records under service `org.ash.jarvis`, with an account hash bound to purpose and endpoint. Secrets never enter subprocess arguments, plaintext files or SQLite. Existing entries are updated, missing entries return no key, denied/locked Keychain access reports its OSStatus. Windows DPAPI code is reached only on Windows. Keychain OS permissions must be granted by the owner; no fallback bypass exists.

Local Mac speech uses `/usr/bin/say` through a cancellable Qt process, with stdin text, system/selected voice, rate and volume. Killing/reaping this app-owned process interrupts speech. Vosk 0.3.44's official universal2 wheel includes the Mac implementation; Windows continues using 0.3.45. Mac packaging verifies a native arm64 Python, loads the real library/model, targets arm64 and adds microphone/Apple Events usage descriptions. These are implemented paths; Windows mocked tests do not constitute Mac hardware verification.

## Source setup on an M1 Mac

Use macOS 12 or newer and native arm64 Python 3.12. Do not use a Rosetta x86 terminal or copy a Windows virtual environment. Obtain the audited source ZIP in the prepared handoff folder or clone `https://github.com/zx-divine/jarvismac`. Extract it to a normal writable project directory, then:

```bash
cd jarvismac
bash scripts/setup_macos.sh
.venv/bin/python -m jarvis
```

The default private data directory is `~/Library/Application Support/ASH-JARVIS`. The API key is optional for local functionality. Wake manually first. In Settings explicitly enable microphone access and the local standby detector to recognize “Wake up, Jarvis” and “Jarvis, go to sleep”. Without a Gemini key, recognized local commands such as `system status`, `what time is it` and `open calculator` work through the approved tool registry. Arbitrary AI conversation explains that a key/model is needed.

In **System Settings → Privacy & Security → Microphone**, approve JARVIS for packaged execution or your terminal/Python host for source execution. Select a real input device in Settings and use **Logs → Test Microphone** while awake. Test Speaker uses the OS default output. Give Automation permission only when a specific approved native tool needs it. Screen Recording is needed only for an approved screenshot. This port does not require blanket Accessibility or Full Disk Access; it does not implement arbitrary UI control. If macOS requests a permission, review and grant it yourself.

Hard Mute closes JARVIS microphone streams and invalidates queued recognition; leave it manually. TTS is half duplex on both platforms. During speech use Sleep/Stop Speaking/Hard Mute to interrupt.

## Native .app build

```bash
bash scripts/build_macos.sh
open dist/JARVIS.app
```

The script installs Mac dependencies, runs tests, downloads/loads Vosk, builds `dist/JARVIS.app`, verifies its ad-hoc code signature, launches a no-key/no-microphone package smoke check and creates `dist/JARVIS-macos-arm64.zip`. The PyInstaller spec sets `NSMicrophoneUsageDescription` and `NSAppleEventsUsageDescription`. Ad-hoc signing does not replace Developer ID signing/notarization. No certificate or Apple credentials are supplied; neither signing identity nor Gatekeeper is bypassed. Review an unsigned/ad-hoc app through normal macOS security controls or build trusted source locally.

GitHub Actions uses the documented `macos-15` Apple Silicon runner, checks the actual architecture and produces the ZIP only if tests, native load and package launch succeed. A hosted runner cannot establish your M1 microphone, room accuracy, output hardware, Automation consent or notarized distribution behavior.

## Required real-Mac acceptance

Verify Keychain save/read/update/delete with a dummy credential; initial no-key startup; native .app paths; local speaker completion/interruption; live microphone wake and sleep; rapid cycles; unplug/reconnect and wrong-device selection; Hard Mute during capture/playback and after unmute; normal OS permission denials; Finder/VS Code/Music/volume actions with consent; screenshot privacy; power cancellation without actually powering off during routine QA. No Mac test or .app is claimed until a real Mac runner/device executes it.

Implementation references: [Apple SecItem password storage](https://developer.apple.com/documentation/security/adding-a-password-to-the-keychain), [Vosk supported platforms](https://alphacephei.com/vosk/install), [PyInstaller macOS bundling](https://pyinstaller.org/en/latest/spec-files.html), [GitHub hosted runner architectures](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).

Windows preparation also downloaded the Mac native wheels and inspected their Mach-O headers: 449 images across 15 wheels all contain arm64, including Vosk's `libvosk.dyld`. The Mac specification explicitly classifies that unusual suffix as native code for PyInstaller architecture processing and ad-hoc signing. This is dependency inspection, not Mac execution or a native application build.
