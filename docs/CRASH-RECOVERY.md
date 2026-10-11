# Windows crash recovery evidence

## Confirmed native crash, 11 October 2026

Windows Application events 1000/1001 at 22:05:47 / 22:05:52 local time identify `JARVIS.exe`, `VCRUNTIME140.dll` 14.44.35211.0, exception `0xc0000005`, offset `0x12196`. The owner's Python crash log was empty. Windows Error Reporting retained metadata but no accessible minidump with symbols, so the exact C++ instruction cannot be identified.

Reproduction on the same Windows host: `python scripts/recovery_probe.py --microphone`. At step 0 the app wakes and calls `tts.say()`; at step 1 Sleep interrupts it. The process exits 1 with a native access violation. The same probe **without microphone capture** fails at the same transition, isolating the speech path rather than Vosk/microphone or missing Gemini credentials. Faulthandler recorded the GUI in `jarvis/ui.py:wake` and then the Qt event loop. Local raw evidence is retained in the ignored `.recovery` directory. No microphone samples or private conversations are in these traces.

Fix: replace Qt 6.8.3's in-process SAPI speech execution with an asynchronous, interruptible Windows `System.Speech` subprocess. COM/native synthesis lives in that process; Stop/Sleep/Hard Mute terminate and reap it. Speech text travels over stdin, never command arguments or a disk recording. Native speech voice selection, rate, volume and cloud TTS remain supported.

An expanded test sequence also reproduced a Qt abort after a speech process was destroyed and later UI events were processed. Replacing process callbacks that closed over QObject lifetimes with receiver-bound Qt slots resolved that sequence (12 tests passed). This additional failure is distinct from the owner's original crash.

Other targeted repairs: physical PortAudio abort/close on mute; cancellation before stream creation; discard cancelled audio; generation checks after recognition; preserve cold-loading listener ownership; cache Vosk models to avoid repeated native loads; bounded retry on disconnect; tolerate isolated input overflow; invalidate voice events even across a mute/unmute cycle. Hard Mute also cancels pending work and speech. Multiple app instances share a local instance lock. Native stack logging now runs during normal launches.

Offline commands (`system status`, `what time is it`, `open calculator`, allowlisted app/media commands) pass through the existing approval registry. When Gemini has no key, the local listener uses its already-local transcript; arbitrary conversation receives the original clear missing-key guidance. No fake AI replies or automatic tool execution were added.

Corrupt SQLite files are preserved privately before safe replacement. Invalid saved preferences remain in the database until explicitly saved; startup uses microphone-off defaults. Locked or permission-denied databases are not treated as corruption.

## Reproduction and acceptance limits

`scripts/recovery_probe.py` deliberately uses microphone capture only with `--microphone`; it does not save/upload audio. It exercises manual wake/sleep/mute/stop transitions and native speech interruption. It cannot establish that a human wake phrase was spoken into the microphone. Run the owner's live wake/sleep acceptance test after enabling microphone permission and the local detector in Settings.

Speech remains half duplex; listening pauses while TTS plays. During playback use Sleep/Stop Speaking/Hard Mute. The app does not implement acoustic echo cancellation. A stopped microphone stream belongs only to this application; it cannot mute other applications' capture.
