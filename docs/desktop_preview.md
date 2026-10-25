# Same-UI Desktop Preview — internal macOS arm64 prototype

This is a separate packaging experiment. The browser/source beta remains the main setup-required download. No public desktop release, signing purchase, portfolio change or paid model call is authorized by preparing this prototype.

## Runtime design

A small Electron shell opens the exact production Next.js interface and existing FastAPI engine. The existing server bridge, research contracts, storage, lexical retrieval, source integrity, drafts and human proposal-review rules are reused. There is no static rewrite, second frontend or second research engine.

Electron45.0.0 is pinned in `apps/desktop/runtime-lock.json`, including its official archive SHA256. Its separate `utilityProcess` executes the traced Next.js standalone server using Electron's **bundled Node**, not a system `node` or the renderer/main event loop. The package explicitly includes `.next/static` and any `public` files omitted by default standalone output.

The Python sidecar is the pinned python-build-standalone CPython3.12.15+20261021 **aarch64-apple-darwin** install-only distribution, with its official archive SHA256. The exact corresponding full upstream build archive is separately pinned only to retain all20 upstream binary-dependency license files and a target/license metadata projection; its build objects are never shipped. Public upstream build-machine fields are omitted from that projection. The existing locked CPU API dependencies are installed into that packaged runtime at build time. A copied developer virtual environment is not used. Runtime startup removes developer PATH entries and inherited provider/hosted/proxy settings. No pip/npm/pnpm/Docker/build/model download runs at first launch.

Use the explicit builder runtime-fetch stage only to obtain verified build inputs. Build prerequisites remain build-time tools, not installed-user requirements. The final artifact's actual launch evidence decides whether the core app is self-contained; source code alone does not establish this.

## Isolation and security

The default new data root is `~/Library/Application Support/LiteratureReviewEngineDesktopPreview`; engine state and a dedicated persistent browser partition live outside the application. It does not open browser-beta/Track B databases, copy cookies or migrate existing workspaces. Replacing/removing the app does not erase this data. Optional models and caches are not part of the signed bundle.

One instance owns the dedicated profile. The Python store has an exclusive live lock. The shell checks ports43000/48765 before starting and verifies the listener PIDs plus both health endpoints before opening the UI. It never attaches to or kills an unidentified listener. Owned services stop on normal quit; the Python sidecar monitors parent loss. Orphaned/conflicting listeners fail closed and need verified operator recovery; recorded PIDs are never trusted as kill authority.

The renderer uses sandboxing, context isolation, no Node integration and no preload/renderer IPC API. Only the owned exact loopback origin can load. Navigation, external HTTPS citation destinations and native export downloads are allowlisted. Renderer permissions are denied. Existing Host/Origin/CSRF/request-size/no-store protections remain. No `webSecurity:false`, wildcard CORS, `null` origin, file-page bypass or operating-system protection bypass is used.

Cloud keys remain per application-session backend memory, never an OS-keychain claim. No Remember key feature is provided. Existing cookie expiry/access-recovery limits remain; a persistent desktop partition is not authenticated transfer or account recovery.

## Features and limits

The required base experiment is the saved/manual workflow: public example, local imports, comparison → passage search → exact source → return, draft/submitted revisions, exports, settings and reopening. Optional local/own-key cloud chat adapters use the same backend. They need separately operated server/account credentials and explicit one-run consent; no live provider tests are included by implication.

New BGE maps need separately installed optional ML dependencies/weights. Those are not bundled, and this internal desktop preview does not supply an external optional-ML installer. The saved map continues to work without them. Do not mutate the application bundle with pip or claim the optional ML stack is included.

Public trusted macOS installation requires a complete binary notice/SBOM review, Developer ID signing of nested code and the final bundle, hardened runtime/entitlement review, Apple notarization/stapling and actual downloaded/quarantined-device tests. An ad-hoc signature used for local internal tests is **not** Developer ID signing, notarization or Gatekeeper approval. Do not disable Gatekeeper; no paid certificate/account is purchased here.

## Measurements and evidence

The evaluation record must distinguish build success from actual bundle execution with developer runtimes unavailable. Record compressed/installed bytes, included executable paths/versions, cold readiness/window time, idle/working memory, shutdown/reopen, port conflicts, app replacement, and visual/keyboard/manual-workflow results. List skips and failures. Linux/Windows desktop support is not claimed.

## Observed packaging integrity correction

The first internal build exposed absolute developer checkout roots in generated Next server/config metadata and non-relocatable install-prefix shebangs in three unused Python console scripts. The builder now derives only those observed Next build roots from the packaged server directory, keeps required-server appDir relative, removes the unused console entry scripts (the app invokes packaged Python directly), and refuses generated payloads retaining the owner home, checkout or build-output path. This transformation is recorded in DESKTOP_RELEASE.json and checked before signing. The first internal archive is superseded and must not be distributed as the successor.

The first actual desktop launch failed before creating a research window: the initial prototype had retained the executable name Electron, which Electron45 treats as an unpackaged development app. The builder now gives the actual binary a product name and matching CFBundleExecutable. The original packaged-app guard stays enabled; no force-is-packaged flag or security bypass is used. The failed attempt exercised zero research operations.

A second actual startup attempt reached the service process but exposed an overly broad archive filter: excluding every directory named trace also removed Next.js required next/dist/trace runtime modules. The builder now retains those traced dependencies. The diagnosis used a disposable copy under Electron45 Node24.22.0; it did not replace the packaged Node runtime with a developer executable.
