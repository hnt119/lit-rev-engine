# Windows x64 experimental desktop build

**Experimental Windows beta — not yet tested on Windows.** This is a private build checkpoint for [issue #18](https://github.com/hnt119/lit-rev-engine/issues/18), not a public Windows release or a compatibility claim. The published Mac DMG and source releases are unchanged.

The existing Electron/Next.js/FastAPI/Python application and NSIS installer are reused. Version **0.3.0-desktop-beta.2**, build **3002**, remains a separate native channel from source beta.4. The original private Windows candidate and its hashes are preserved; a fresh output directory identifies the new build.

## Intended installation

1. Obtain the reviewed `Literature Review Engine Setup 0.3.0-desktop-beta.2.exe` and its matching manifest/checksums from the owner. There is currently **no public Windows asset URL**.
2. Check the file's SHA-256 against the supplied checksum. This installer is unsigned; ordinary Windows download/security behavior has not been observed. Stop if Windows blocks it or reports malware, damage or an integrity error. Do not disable Defender/SmartScreen or remove download-origin markings.
3. Run Setup for your current user. The existing installer targets **Windows 11 x64**, without administrator elevation. Windows 10, Windows ARM and 32-bit Windows are rejected by its existing platform checks; this task does not expand that target.
4. Open **Literature Review Engine** from Start. Choose **Try the saved example**, or configure research settings later. This sequence is the intended experience, not a completed Windows acceptance test.

Core bundles Electron's Node runtime, CPython, the production frontend, backend dependencies and the permitted saved example. Users should not install Python, Node, pnpm, Docker or models to use Core. Welcome, optional AI settings, source-linked comparison, explicit excerpt selection, drafts, revisions and native exports use the same application implementation.

Qwen/MedCPT libraries and model weights are not bundled. A Windows optional neural-library capsule is unavailable. New BGE map fitting needs its separate dependencies; the saved map does not. Existing local/OpenAI/DeepSeek generation configuration and consent remain optional; a saved setting is not a successful provider check. No model download, provider call, indexing or search should run merely from opening or skipping setup.

## Installation, storage and removal policy

- Application: `%LOCALAPPDATA%\Programs\Literature Review Engine\app-0.3.0-desktop-beta.2`.
- Research/profile state: `%LOCALAPPDATA%\LiteratureReviewEngineDesktop`, outside application files. No browser-beta, prototype or Track B data is opened or migrated automatically.
- Setup creates per-user Start menu application/uninstall entries and the normal Windows uninstall registration. A matching version already installed must be uninstalled before reinstalling that version.
- The existing uninstall helper removes only verified application files and preserves research by default. Unexpected or modified application files are retained for inspection. Running/foreign processes and unsafe installation paths cause refusal rather than termination or permission repair.
- Session-entered provider keys are memory-only. Cookie/profile loss can prevent access to retained workspaces; CSV/JSON exports are research outputs, not complete authorization backups. Preserve complete stopped state privately before replacement.

These are source/configuration and package-policy observations. Start menu launch, actual saves, shutdown, reinstall and uninstall behavior on Windows remain **NOT_RUN**.

The retained pywin32 wheel also contains GUI, MAPI and debugger extensions that Core does not import. Static inspection of the existing candidate found unresolved MFC/C++ runtime imports in those extra modules and a debugger sibling-module lookup. They are not silently classified as Windows OS files or fixed by removing libraries. The new packet reports declared Python dependency closure and the complete bundled native-library audit separately; a full-wheel audit with unresolved imports is not labeled passed.

## Build and integrity review

Build from an exact clean committed source, using the existing locked build-time tools and a new external output directory:

1. Produce the internal engine source snapshot with `scripts/build_local_preview.py`; its beta.4 filename is an internal convention, not a replacement public source release.
2. Build only the production standalone frontend with the existing `LITREV_DESKTOP_STANDALONE` configuration and clean local build environment. Generate its exhaustive source-bound standalone/static/public inventory. Do not rebuild the Mac application.
3. Use `scripts/build_desktop_installers.py --target win32-x64` with that source archive/commit, web binding, pinned Windows Electron/Python archives and pinned NSIS compiler/SDK. Dependencies are assembled on the Mac; Windows executables are not run.
4. Check the complete installed-file manifest, target PE architectures, Windows dependency metadata and bundled DLL closure. Inspect the generated Setup.exe as a real NSIS PE, extract it without executing it, and compare its application payload to the manifest.
5. Generate the final file manifest, SBOM/native inventory, source/build provenance, SHA256SUMS, installation guide and release notes outside the source checkout. The exact source SHA, installer bytes/hash, commands and results belong in that artifact packet.

Original engine code is MIT. Electron/Chromium/Node, Python, NSIS, Python wheels, FFmpeg and Microsoft runtime files retain their own terms. Windows-specific notices and exact binary/source bindings must accompany this target; Mac qualification does not satisfy them. The packet distinguishes retained notices/corresponding source from any unresolved owner redistribution permission. An SBOM or successful build is not legal certification.

## Disclosed test scope

| Check | Scope |
| --- | --- |
| Production build and NSIS compilation | Run on macOS; final observed results in the artifact packet |
| Payload hashes, dependency completeness and installer policy | Static/package checks where possible on macOS |
| Windows installation/execution | **NOT_RUN — skipped by owner for this task** |
| Physical Windows 10/11, Windows VM or GUI automation | **NOT_RUN — explicitly out of scope** |
| Installed-app workflow, download-origin/security behavior and Authenticode trust | **NOT_RUN**; installer remains unsigned |
| Models, live PubMed, cloud generation, scientific/human usefulness | **NOT_RUN** |

## README and publication handoff

The repository keeps its existing direct Mac DMG and plain **Windows installer not yet published** status. The source setup fallback remains labeled separately. There is no invented EXE URL, placeholder download button or private candidate upload.

If the owner later authorizes publication, review the exact Windows packet and outstanding redistribution conditions first. Use a new actual GitHub Release asset, anonymously download and verify its final bytes, then replace the Windows status with that real `browser_download_url`. Keep **experimental Windows beta — not yet tested on Windows** next to the download until Windows execution evidence exists. Public upload, signing purchase and publication are not authorized by this build task.
