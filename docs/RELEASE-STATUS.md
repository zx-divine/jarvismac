# Mac repository release status

Repository: https://github.com/zx-divine/jarvismac, branch `main`.

The Mac-specific layout uses `.command` launchers, arm64 dependencies and a Mac-only packaging workflow. Shared application modules remain intact to preserve Gemini, alternative providers, memory, voice, permissions and security.

The original shared-source native macOS workflow succeeded in run 38399065467. The layout correction triggers a new workflow whose actual result is reported separately. Git history is preserved; Windows launcher removal applies to the current source tree.

Secrets, private state, models, virtual environments and generated packages are excluded. Authentication must use existing authorization; never retrieve verification codes or bypass macOS/GitHub protections.
