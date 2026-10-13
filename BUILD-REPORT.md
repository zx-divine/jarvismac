# Apple Silicon build status

The original source commit `59dd55ded1402342c431d714329d529fd2e7cf7c` completed the native macOS CI job successfully in [run 38399065467](https://github.com/zx-divine/jarvismac/actions/runs/38399065467). GitHub reported a non-expired `JARVIS-macos-arm64` artifact of 108,427,515 bytes when checked on 13 October 2026.

This correction removes Windows launchers and environment manifests, supplies executable Mac launchers and Mac-first documentation, and limits this repository's CI to Apple Silicon. Application modules and tests are preserved. The correction will receive a separate native CI run; its outcome must be checked before treating the new package as verified.

No native Mac package was built locally on the Windows development computer. Hosted CI success does not establish live M1 microphone, speech accuracy, Keychain consent, Automation/Screen Recording permission or notarization. See docs/MACOS.md for hardware acceptance.
