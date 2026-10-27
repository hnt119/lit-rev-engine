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

The Windows Core packaging policy omits only three reviewed optional pywin32 directories: `pythonwin`, `win32comext/mapi` and `win32comext/axdebug`. These provide Pythonwin/DDE/MFC user interfaces, Outlook/Exchange MAPI integration and ActiveScript debugging. The actual application uses none of these interfaces. Its pywin32 security, ACL, file/lock, named-pipe, process/job and native-export dependencies, loader/bootstrap, metadata and licenses remain bundled.

The build verifies a pinned file/hash policy and wheel RECORD before removing anything, and records each omitted file in build metadata. The static audit checks the receipt, protected files, application imports and **all retained PE imports**. It does not waive MFC/MSVCP warnings by calling them operating-system DLLs. Some retained third-party pywin32 demos/helpers refer to the omitted APIs; this is a Core-specific subset, not a complete pywin32 developer installation. Arbitrarily constructed dynamic imports and Windows loader behavior remain untested.

## Build and integrity review

Build from an exact clean committed source, using the existing locked build-time tools and a new external output directory:

1. Produce the internal engine source snapshot with `scripts/build_local_preview.py`; its beta.4 filename is an internal convention, not a replacement public source release.
2. Build only the production standalone frontend with the existing `LITREV_DESKTOP_STANDALONE` configuration and clean local build environment. Generate its exhaustive source-bound standalone/static/public inventory. Do not rebuild the Mac application.
3. Use `scripts/build_desktop_installers.py --target win32-x64` with that source archive/commit, web binding, pinned Windows Electron/Python archives and pinned NSIS compiler/SDK. Dependencies are assembled on the Mac; Windows executables are not run.
4. Check the complete installed-file manifest, target PE architectures, Windows dependency metadata and bundled DLL closure. Inspect the generated Setup.exe as a real NSIS PE, extract it without executing it, and compare its application payload to the manifest.
5. Generate the final file manifest, SBOM/native inventory, source/build provenance, SHA256SUMS, installation guide and release notes outside the source checkout. The exact source SHA, installer bytes/hash, commands and results belong in that artifact packet.

Original engine code is MIT. Electron/Chromium/Node, Python, NSIS, Python wheels, FFmpeg and Microsoft runtime files retain their own terms. Windows-specific notices and exact binary/source bindings must accompany this target; Mac qualification does not satisfy them. The packet distinguishes retained notices/corresponding source from any unresolved owner redistribution permission. An SBOM or successful build is not legal certification.

The [Microsoft redistribution review](windows_redistribution_review.md) identifies the exact conditional grants, required accompanying material and unresolved owner decisions. Retaining the upstream terms does not itself establish distributor/end-user agreement. A candidate with unresolved conditions stays private; a successful static dependency check does not remove that publication gate.

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

## Observed cross-build — 28 October 2026

Built from clean source **`1d1bd96e98673015e4cc294cc3b5b6c922764ebb`**. This later documentation/evaluation update does not change the executable or imply a rebuild from the documentation head.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `Literature Review Engine Setup 0.3.0-desktop-beta.2.exe` | 197099124 | `42858d5ea8d1a907c913c2b8538f278ecc15b529784aa6ba87c80819b26a0188` |
| Installed-file manifest | 1518531 | `b55db191e7bf0bc99b14d9a2859b102c21f8d3e48b6599fb86e2b9ff65a2c6ec` |

The source audit, real production frontend/TypeScript build, Windows assembly and macOS-host NSIS compilation passed. The final host policy/package batch passed **97 Python tests**, with zero failures/skips; the separate Node security/session/export contract batch passed **23 tests**, with zero failures/skips. These tests used host fixtures/mocks and do not qualify Windows execution.

Host-only 7-Zip extraction verified the complete **7581-file** installed payload against the exact manifest, with no missing/extra files; the payload contains **7582 files including the manifest**. Required Core file presence and Windows-target CPython 3.12 AMD64 metadata closure passed (17 distributions; 16 wheel installs plus runtime-bundled pip). The x86 NSIS bootstrap and AMD64 application/Python files are distinct; the installer has no embedded Authenticode certificate table.

The full bundled native import audit **FAILED** with seven retained extra-module edges: four Pythonwin imports of `mfc140u.dll`, two MAPI imports of `msvcp140.dll`, and the axdebug import of `axscript.pyd`. None was waved through as an OS library or removed blindly. The audit separately records 685 declared OS/API-set edges without claiming their availability or exports were tested on Windows.

The final Windows notice copy verified 15 input files, five exact DLLs and two retained runtime licenses. Both exact FFmpeg source companions passed hashes and target correspondence; the SBOM/native inventory records 160 metadata components and 120 native files. The [Windows notice record](../apps/desktop/notices/windows-runtime/README.md) retains two concrete owner actions: applicable Microsoft SDK redistribution permission/conditions and the Windows Python downstream protective-terms mechanism. No agreement was accepted for the owner and no Visual Studio purchase requirement is inferred.

Windows runtime, installation, VM, GUI, installed workflow, download/security and real-model/provider checks are **NOT_RUN**. The old candidate, published Mac/source releases, original research, Track B, phone prototype and personal website were preserved. No upload, push, tag, main merge, paid service or publication occurred. The final private packet contains installation notes, complete audit receipts, source/build provenance, corresponding-source material, manifests and checksums; it is not a public release.

## Optional-component subset release candidate — 28 October 2026

New clean build source: **`8566e225a1c4e8d25de76d984f80fcb346deae79`**. Product version/build remain **0.3.0-desktop-beta.2 / 3002**. This is a separate private Windows candidate; existing Mac/source assets and earlier private candidates are unchanged.

| Final artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `Literature Review Engine Setup 0.3.0-desktop-beta.2.exe` | 195446034 | `6381a46f766024078093ef0c46ddf0fecd200197859f0688aa732279bd58491d` |
| Installed-file manifest | 1492982 | `dbbada2784954fc1e737e8ce5bd560911336b485b9c2a279defa0a020aba3fff` |

The clean-source snapshot, real production frontend build and macOS-host NSIS compilation passed. The final committed-source host batch passed **140 Python tests** and **23 Node tests**, with zero failures/skips. These are packaging/policy and mock/fixture checks, not Windows application execution.

Independent host archive testing, safe-path inspection and extraction passed. All **7447 manifest entries** matched exactly; the payload contains **7448 regular files including the manifest**, without symlinks. All **112 retained PE files** were scanned, with **zero unresolved declared import/delay-import names** under the unchanged explicit Windows OS/API-set assumptions. The **626 OS/API-set edges** and their exported symbols/loader behavior were not tested on Windows. Windows-target dependency metadata closure passed for **17 distributions**; application source scanning passed for **126 Python files**, with no direct/literal imports of omitted APIs. Arbitrary computed imports remain outside that check.

Exactly **136 files / 4522690 bytes** were omitted from the three reviewed optional directories. Their eight PE files include the seven offending parents and Pythonwin's companion Scintilla DLL. The complete old/new Python comparison confirmed **4345 retained files / 85012816 bytes** unchanged, including **34 protected Core/bootstrap/metadata/license files**. The original wheel RECORD remains intact; the hash-bound subset receipt explains the omissions and verifies its **610 file declarations**. The packaged policy is not a claim that every pywin32 developer API remains available.

An intermediate build from **`03308c956be4e933a349923658d7afbcf3c1b6c6`** failed the independent final-inventory check: its subset receipt preceded copying 21 attribution files. That artifact (SHA-256 `ceda0e32189cc667ed5f937890df82ff18dbbff74c35e0c0b13bb869b573889e`) and failure evidence were preserved. The final source moves the receipt after attribution, adds a regression guard, and was rebuilt/re-extracted in a fresh directory. The failed build is not a release candidate.

The regenerated SBOM records **160 metadata components**, **112 native files** and **zero missing-notice review items**. This does not resolve conditional redistribution permission: the [two Microsoft owner decisions](windows_redistribution_review.md) still block public upload. Exact SDK/Python DLLs and terms, all prior third-party notices, and both matching FFmpeg source companions remain required. No agreement was accepted or replaced by the engine MIT license.

**Windows 11 x64 — experimental, unsigned, not tested on Windows.** The Setup PE has no embedded Authenticode certificate table. Installation, Start menu launch, actual workflow/exports/restart/uninstall, Defender/SmartScreen/download-origin behavior, Windows OS availability, VM and GUI execution are **NOT_RUN**, explicitly excluded by the owner. Real models/providers, live PubMed and scientific validation are **NOT_RUN**. The proposed separate tag `v0.3.0-windows-experimental-beta.2` has not been created. No Windows URL exists; README continues to show Windows unavailable. Publication requires resolving the Microsoft conditions and separate owner approval.
