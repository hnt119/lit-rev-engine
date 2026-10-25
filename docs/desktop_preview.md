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

## Immutable application resources

Post-workflow manifest verification caught Next.js promoting the public license page into a route cache inside the signed bundle. The desktop runtime now uses the documented Next cache-handler interface to decline persistent derived page/image caching. The browser/source distribution cache behavior and all research SQLite/source stores remain unchanged; Electron profile state and research data stay in the external Desktop Preview root. This does not change retrieval, HTTP no-store policy or source bindings. Final validation must recheck the complete signed bundle after the workflow, including license/about navigation.

## Web dependency notice inventory

Next standalone tracing omitted dependency notice files, so the builder separately preserves exact notices from matching locked installed package metadata. Resources/WEB_DEPENDENCY_NOTICES contains per-file hashes, original relative source paths, declared licenses, native component versions and upstream repository/source links, including nested Next compiled packages. The initial inventory covers67 package metadata entries and113 unique notice files. Seven upstream full-notice sources remain explicitly unresolved (including the native libvips package and several Next-compiled packages); source/redistribution obligations and a complete transitive binary SBOM need review before public desktop distribution. This does not change the engine MIT grant or block the separate source-only browser candidate.


## Actual internal candidate and local use

The reviewed artifact source is `d2ae854f9626ac2a3f7f38cbcd358d5519cdd562`, version `0.3.0-desktop-preview.1`. It is separate from the setup-required `0.3.0-beta.2` source ZIP. Both are unpublished. See [the exact artifact hashes and capability matrix](releases/v0.3.0-beta.2-review.md) and [executed checks, failures and limits](next_beta_evaluation.md#final-extracted-desktop-execution--d2ae854).

For an owner-reviewed local copy, first verify the matching SHA256SUMS, then extract the ZIP. Open **Literature Review Engine Desktop Preview.app**. The saved/manual application does not require a Terminal window or a separately installed Python/Node/pnpm/Docker. It starts only its packaged production services and opens after ownership/readiness checks. Choose **Saved example · offline** to begin without credentials or models. Use application-menu **Quit** to stop owned services; closing its sole research window also quits. macOS may refuse an unnotarized downloaded copy; do not disable Gatekeeper or remove quarantine to bypass that refusal. This locally tested prototype is not yet a trusted public installer.

Research and profile state live in the separate Desktop Preview application-support directory described above. Keep it private; do not point the prototype at existing browser-beta or pilot state. App replacement after a controlled quit preserves that directory. Do not copy a running database, delete active locks, kill an arbitrary port listener or treat a workspace UUID as authorization. If startup reports an occupied port, close only the positively identified conflicting application and retry; the prototype will not attach to it. A cookie/profile reset or expiry can make retained work inaccessible under the existing access model. Export while access is available; no new recovery/transfer system is included. Backend restart clears cloud keys and they must be re-entered in Settings.

Settings is the same production page as the source beta. Local/OpenAI/DeepSeek generation is optional, default-off and separately consented; no live account/model check was authorized. The desktop has the base API runtime and real adapters, but does not operate a local model server or bundle weights. The map-cache preference is inactive until operator configuration is supplied; it does not install the absent ML stack. Use the source beta for the explicitly supported optional map setup.

The actual core launch used bundled Node **24.22.0** and Python **3.12.15**, with developer PATH entries removed. The compressed ZIP is **163,840,256 bytes**, installed payload **390,961,851 bytes**. The app reported 1.935 s readiness / 2.210 s visible window on its first measured UI run; instrumented first-window total was 6.288 s. Reopen totals were 2.373 s ready / 2.584 s visible / 2.855 s including instrumentation. A separate lifecycle run measured 2.503 s ready and 5.560 s after extraction/replacement. These single-machine timings may benefit from warm disk caches. Sampled process RSS sum was **667.31 MiB idle / 827.42 MiB working**, including shared pages more than once. Visual theme/typography/navigation and keyboard cell-return checks passed against Chrome at the same viewport; pixel equality is not asserted.

Actual native Save dialogs, external citation opening, menu Quit, single-instance handoff, owned-parent crash cleanup, port conflicts, app replacement, data/draft/exports preservation and final signed-bundle immutability passed. Physical sleep/wake and quarantined-device installation were not run. Only macOS arm64 was evaluated.

## Exact public desktop distribution blockers

The seven explicit full-notice gaps are `@img/sharp-libvips-darwin-arm64` 1.3.4, `@next/env` 16.4.2, `client-only` 0.0.1, and Next-vendored `@edge-runtime/cookies`, `@edge-runtime/ponyfill`, `@edge-runtime/primitives` and `string-hash`. Existing declarations/source links are retained; they are not substituted for absent full texts. The original code stays MIT. Before public desktop distribution, resolve the appropriate notices and any binary/source obligations, complete the transitive SBOM/license review, then review hardened-runtime entitlements, Developer ID nested-code signing, notarization/stapling and downloaded/quarantined-device behavior. Publication needs separate owner authorization. No signing account was bought and no operating-system security was bypassed.

## Reproduce a reviewed build

Use a clean checkout of the exact artifact SHA, macOS arm64 and the existing locked build tools. Outputs and runtime caches belong outside the checkout. The source builder refuses dirty/untracked release inputs; the desktop builder checks the exact clean source ZIP and verified runtime hashes. Runtime acquisition is an explicit build-time download, never a model or first-launch download.

```sh
python3.12 scripts/build_local_preview.py --help
python3.12 scripts/build_desktop_preview.py --runtime-cache /path/to/runtime-cache --fetch-runtimes
python3.12 scripts/build_desktop_preview.py \
  --runtime-cache /path/to/runtime-cache \
  --source-archive /path/to/lit-rev-engine-0.3.0-beta.2.zip \
  --expected-source-commit d2ae854f9626ac2a3f7f38cbcd358d5519cdd562 \
  --output /path/to/new-empty-output \
  --node /path/to/node24 --pnpm /path/to/pnpm10.20.0
```

The generated source ZIP was independently reproduced byte-for-byte. The desktop builder records exact source/runtime/file hashes, but byte-for-byte desktop signing/archive reproducibility was not demonstrated. Keep its manifest, checksums and source identity together; do not reuse a superseded archive's checksum.
