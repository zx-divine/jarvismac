# macOS verification record

On 13 October 2026, GitHub reported success for the native macOS job in [run 38399065467](https://github.com/zx-divine/jarvismac/actions/runs/38399065467), using source commit `59dd55ded1402342c431d714329d529fd2e7cf7c`. The job runs the source audit, native arm64 build script, tests, Vosk library/model load, PyInstaller package, ad-hoc signature verification and no-key package launch, then uploads `JARVIS-macos-arm64`.

The Mac-specific repository layout correction must pass its own CI run. No local Windows rebuild is used to claim Mac verification.

Real provider API calls require the owner's credentials. Tests use dummy credentials and mocked provider responses and do not establish account model availability, quota or billing. Hosted CI does not establish live owner-microphone wake accuracy, physical device reconnection, native Keychain consent, screenshot/Automation permissions, power actions or Developer ID notarization.

Follow the real-Mac acceptance checklist in [MACOS.md](MACOS.md). Speech remains half duplex; use UI Sleep/Stop Speaking/Hard Mute to interrupt playback.
