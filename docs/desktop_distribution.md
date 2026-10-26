# Native desktop distribution — private candidate

This is the separate `0.3.0-desktop-beta.1` packaging checkpoint, not a replacement for the published setup-required source beta. It reuses the reviewed Track A production Next.js/React UI and FastAPI/Python engine. The current README continues to link to the published source release until native release gates pass and publication is authorized.

## Installation and data

The macOS Apple Silicon DMG contains **Literature Review Engine.app**, an **Applications** shortcut and installation instructions. Drag the application into Applications, eject the DMG, then open the installed copy. Running from the mounted image, a translocated location or the build directory is rejected. The Electron runtime declares macOS 13.0 as its minimum; the actual tested host and limitations belong in the candidate's external evaluation report, not a claim that every supported OS was tested.

The Windows candidate is an NSIS per-user **Setup.exe**, targeting Windows 11 x64. It installs under `%LOCALAPPDATA%\Programs\Literature Review Engine`, creates Start menu application/uninstall entries, and requires no administrator setup. Its fixed application location cannot be redirected to a research folder. Actual installed Windows execution is unverified until it is tested on Windows; a cross-built installer and source tests are not that evidence.

Node runs through the bundled Electron utility process. The core interpreter and dependencies are bundled Python. Core research needs no system Python, Node, pnpm, Docker, compiler, Terminal window, model download or provider key. The application removes inherited developer/provider configuration and selects loopback-only local mode explicitly. It refuses occupied ports rather than terminating other applications.

Research and browser state live outside immutable application files:

| Platform | Dedicated native data location |
| --- | --- |
| macOS | `~/Library/Application Support/LiteratureReviewEngineDesktop` |
| Windows | `%LOCALAPPDATA%\LiteratureReviewEngineDesktop` |

Browser-beta, Track B and earlier Desktop Preview data are not opened, scanned or migrated. The native browser uses its own persistent partition. Save drafts before quitting; closing with unsaved input requires an explicit decision. A normal replacement of application files preserves this dedicated data directory. Windows uninstall removes only registered, manifest-bound application files and leaves modified/unexpected files and research data behind. On macOS, removing the application from Applications leaves research data behind. Do not delete the data directory to repair an installation.

## Research, exports and optional capabilities

Core includes the public saved example, bibliography imports, lexical passage retrieval, exact source inspection, comparisons, drafts, revisions and CSV/JSON exports. The existing source/cell return workflow and human review rules remain in use. Opening evidence does not set human support or submit an entry. Research settings and local/OpenAI/DeepSeek adapters retain their existing explicit consent, session credentials and budgets; no live provider call is part of installer testing.

Exports use a native save dialog, an owned-session request to an allowlisted export route, and a bounded atomic file writer. They cannot target application resources or the internal research/profile directory. A canceled dialog writes nothing. If shutdown interrupts a save, inspect the chosen destination; do not assume an ambiguous result was either saved or absent.

Qwen and MedCPT remain optional and experimental in the same UI. Their library runtime is separate from model weights and is installed outside the application using a pinned, verified local capsule. See [optional-runtime installation and recovery](desktop_optional_runtime.md). Installation does not install models, change a profile or run inference. Windows optional runtime is explicitly unavailable. New BGE map fitting requires its separate optional dependencies; viewing saved maps remains available. Missing models or libraries do not silently change a selected retrieval profile to Core.

Session-scoped provider keys are not retained over a backend restart. Workspace access also depends on the native browser's authorization cookie: deleting browser state, changing the data location or using a different browser does not authenticate old workspaces. Keeping only the SQLite files is not a supported cookie-recovery or migration procedure. There is no cloud backup, account recovery or guaranteed recovery after storage loss.

## Rebuilding and integrity

Build from a clean reviewed commit. First create the internal purpose-built engine source snapshot with `scripts/build_local_preview.py --expected-source-commit <full-sha> --output <fresh-directory>`. This internal snapshot keeps the source builder's existing version convention; it is not a republished beta.4 asset. Then invoke `scripts/build_desktop_installers.py --target darwin-arm64` with that archive, exact SHA, verified runtime cache, pinned build-time Node/pnpm and a fresh output directory.

The Mac assembler creates a production standalone web build and records the complete standalone/static/public inventory. Windows assembly requires that exact clean-source web binding, the same audited engine snapshot, pinned Windows runtime archives and pinned NSIS tool input. It verifies all source and web bytes before transforming paths, replacing the reviewed client-boundary compatibility module, omitting the unused native image optimizer and materializing contained web links. Windows target binaries are checked as AMD64 PE inputs; this is not target execution.

Use the final external application inventory, SBOM, build report and checksums to review exact source, runtime, tool and payload bindings. Any source fix or signing/stapling mutation requires a new artifact and new integrity data. Do not replace old released assets or call a stale candidate current.

## Notices and public-release gates

Original engine code is MIT. Bundled runtimes, JavaScript/Python distributions, vendored components, source articles and model weights retain their own terms. License files and exact provenance are retained; the structured SBOM/native inventory records unresolved component versions and source obligations rather than inventing legal clearance.

The original `client-only` bytes with missing full attribution are not redistributed in native payloads: an independent project-owned compatibility module replaces only the reviewed exact three-file input. The unused sharp/libvips image optimizer is disabled and omitted from native payloads; normal research presentation must be exercised without it. These packaging changes do not change source-mode dependencies or claim to resolve upstream terms.

Current native candidates are private. Ad-hoc Mac signing is only an internal integrity mechanism. Developer ID signing, hardened-runtime/entitlement review, notarization and stapling are still required for a trusted macOS release. No signing credentials are available. Do not remove quarantine or bypass Gatekeeper to make a test pass. The correct owner action is to supply authorized signing credentials and complete the normal downloaded-artifact check.

Windows requires an authorized signing method, timestamps and an actual downloaded/installed executable test on Windows. No Windows test machine or signing credentials are available in this session. A signature alone does not guarantee SmartScreen reputation. No account, certificate, paid service, public upload or OS-security exception is authorized by this packaging checkpoint.

Complete final native/vendor source and notice review for both core payloads and the optional capsule, real platform lifecycle tests, signatures and final public-artifact verification before requesting native publication. The external evaluation distinguishes actual application checks, mock tests, source checks, cached real-model integration and unperformed gates.
