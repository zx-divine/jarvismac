# Release status

The Windows repair and shared macOS source are prepared locally. The Windows recovery checkpoint is commit `5e5b165`. The final release commit and publishing outcome are recorded in the final handoff report after the one noninteractive Git push attempt.

Authorized destination: `https://github.com/zx-divine/jarvis`, branch `main`. Initial remote inspection showed an empty repository and no branch refs. No remote history may be force-pushed or deleted.

The safe source audit excludes original private requirement attachments, personal paths, virtual environments, generated executables, models, logs, databases, microphone recordings, caches and encrypted credential files. An `.env.example` contains no key. `.recovery/before-repair.zip` preserves the prior source locally and is ignored by Git.

The GitHub Actions Windows/macOS workflow is prepared. A native Mac .app, Developer ID signature, notarization and real M1 hardware acceptance are pending until an actual Mac runner/device executes the build. Do not treat mocked Mac tests or cross-platform wheel inspection as hardware verification.

Authentication policy: attempt publishing only with existing authentication and terminal/browser prompts disabled. If authentication/2FA/manual consent is requested, stop immediately, retain local commits, and report **GitHub push pending — authentication required.** Never open an authenticator or retrieve verification codes. The owner will authenticate later and request resumption. No push retry or alternate credential path is authorized after such a blocker.


Actual publishing attempt: Git push exited 128: Cannot prompt because user interactivity has been disabled; unable to get password from user. **GitHub push pending — authentication required.** No retry, login window, authenticator, code retrieval or alternate credential path followed. The complete tested source is preserved locally on main (implementation commit e65ac7090900381efd9c8d806d01630efd6ba21d). No commit was pushed; GitHub Actions has not run for this local work. The requested Mac handoff contains the audited source ZIP and setup/report files.
