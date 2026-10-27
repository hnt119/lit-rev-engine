# Private desktop candidate evaluation

This is a partial qualification record, not a native release announcement. Application/installer source: `34f61ec2e3fa1482f4a2b0665f5ced690bd905cf`, on `codex/desktop-distribution`, descended from reviewed main `138bfc91d85cbe45730dd439e77f518fdbfed41d`. Documentation-only follow-ups may follow that source commit; they do not change the artifact binding.

## Independent link and mobile outcomes

PR [#13](https://github.com/hnt119/lit-rev-engine/pull/13) was merged with the owner's explicit approval. Main's Download opens the readable beta.4 release page; Quick start opens its rendered immutable guide. Anonymous Chrome downloads and redirected GETs retrieved the existing source ZIP and INSTALL attachment with their published hashes. The reported download failure was not reproduced; attachment-only Quick start behavior was reproduced and corrected. Fifteen release-link tests passed. Tags and published assets were not changed. See [the exact download diagnosis](releases/v0.3.0-beta.4-download-diagnosis.md).

The phone prototype was saved only in local `codex/review-on-the-go` commit `7232811b2a7718f93499af1d406179966f1d905c`. It is paused, unpushed and absent from native assets. Track B and the actual portfolio were not changed.

## Final built candidates

| Private artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Apple Silicon DMG | 169256870 | `afc0e6fc0f8e07d4e02d02a5f8cbca0676dac0110196fcd64b2028b9da869d3a` |
| Windows x64 Setup.exe | 196850007 | `f17182efa80d7c093e5f5c720fa0b2c684271cd56c3dfe6bc9fde38a0b9b5f4a` |
| Separate Mac optional-library capsule v2 | 171140185 | `736b32b692236427081481793e67556220fb1a8f1b9871addab282a9c4611bb1` |

Version: `0.3.0-desktop-beta.1`. The Mac application contains 372392057 bytes of ordinary files. Both engine payloads bind the same clean source snapshot and complete production web inventory. The separate optional capsule binds its exact reviewed recipe; it contains libraries, not engine code or weights. No native artifact has been uploaded or published. The internal purpose-built engine-input ZIP retains the source builder's beta.4 filename and is **not** a replacement public beta.4 asset.

The Mac candidate is ad-hoc signed and passes strict deep signature verification. The Windows installer is an actual NSIS 3.13 zlib PE executable containing AMD64 Electron/Python payloads, not a renamed archive. Its bootstrap is normally PE32/i386; the application payload and OS guard target Windows 11 x64. Authenticode is absent. No target Windows code was executed on the Mac builder.

## Fresh software checks

- Final source: 190 targeted Python packaging, filesystem, lifecycle, board-passage, settings and consent tests passed; no skips. Two pre-existing FastAPI/Starlette test-client deprecation warnings remain.
- Desktop security/session/native-export contracts: 23 Node tests passed, no skips.
- Frontend: 200 tests passed and TypeScript checking passed. These ran after the UI/runtime-hint change; later corrections changed only packaging and its tests. The final clean production Next build also completed TypeScript checking.
- Both source-bound production builds completed. Mac DMG CRC/manifest and Windows installer/payload bindings passed. Final checksum lists were reread and verified separately.
- An initial Python run skipped one Node-dependent check; the pinned build Node was then supplied and the final run had no skips.

Normal tests use mocks for generation/provider behavior. No live PubMed, OpenAI, DeepSeek or other paid/provider generation call was made. These are software checks, not researcher judgments or scientific validation.

## Actual installed Mac evidence and interruption

Host: macOS 26.6.2, build 25G83, arm64. Electron declares macOS 13.0 as its minimum; other macOS versions were not qualified. This was the existing Mac user with fresh dedicated application state, not a newly provisioned machine or a user account with developer software removed.

Finder copied the application through the DMG's Applications shortcut, and Finder replacement was exercised. Copying while the test app was running was correctly refused; replacement succeeded after normal quit. The image was ejected before installed execution. A reliable literal mouse-drag operation was not established by the automation; the observed installation used Finder copy/paste.

The installed application launched from Applications with stripped developer PATH and bundled runtimes. Actual owned browser-session identity, HTTP-only/SameSite cookie metadata, denied notification/geolocation permission states, renderer isolation and cancellation of an unsupported DownloadItem passed. A public-example workspace was created. The installed candidate now passed the actual three-paper × three-field workflow: explicit candidate retrieval, exact source inspection, excerpt selection, synthetic comments, three unassessed saved entries, field-scoped passage retrieval, return with an unchanged draft/reference, reload, native CSV/JSON exports, normal quit and same-profile reopening. No researcher support judgment was supplied.

Three temporary test-driver errors occurred: a nonexistent Electron permission-query API, reading a URL before asynchronous navigation completed, and an exact label selector that did not match the actual select control. These were harness failures; application source was not changed to make them pass. Original failure reports remain. After the user unlocked the Mac, direct native accessibility controls completed the workflow instead of relabeling the failed automation as a pass.

Actual native Save dialogs produced the initial nine-cell CSV/JSON (three immutable cell revisions), then exports after an explicitly submitted correction (four immutable revisions and three saved cell heads). The original entry remained visible in cell history. A separate read-only validator reused the existing source/board reconstruction methods: all three retained-source bindings, candidate ranges, quotation/hash/range anchors, CSV/JSON cells and successor linkage matched the stored snapshots, with zero SQL changes. All four exported files had mode 0600.

A synthetic local CSV was selected with the native file picker, explicitly parsed, accepted and committed as a one-record collection. No identifier resolution, provider query or source download was requested. The three-paper comparison used full-text saved sources; an abstract-only/missing-information UI case was not added to this native check.

The app menu installed the exact v2 library capsule outside the app. Before restart the backend stayed unchanged; after normal quit/reopen the owned Python process used that verified external capsule. Settings then showed dependencies present while both weight packs remained not installed, rather than claiming model readiness. The unsent note and original references survived reopening; the old submitted table value stayed separate until explicit correction. The synthetic memory-only key changed from KEY PRESENT to NO KEY after restart. A separate Chrome session showed NO KEY and no workspaces, and rejected a direct URL containing the desktop workspace/board identifiers. A scan found no copy of the exact synthetic key marker in 75 inspected QA-state files; this is a bounded check, not a general leakage proof.

The Mac locked again after import. The additional replacement/uninstallation-with-existing-data and ordinary-browser native-download checks are pending; physical sleep/wake, a fresh OS/user with developer tools removed, Intel Mac and other macOS versions remain NOT_RUN. Security settings were not changed to prevent locking. Do not infer these remaining checks from source/component tests.

A separate actual owned-main crash check used only the harness-created public-example process. After SIGKILL of that verified Electron main, its Node/Python services exited, both desktop ports became free, an unrelated sentinel survived, and six inspected temporary SQLite databases returned `integrity_check = ok`. This is crash cleanup evidence, not a completed restart/recovery workflow. All 4102 installed application-manifest entries still matched after execution/crash and again after the native export/library-install workflow; strict deep signature verification remained valid.

Observed performance is a single instrumented host observation, not a benchmark: initial Core readiness 2750 ms, window visible 3164 ms; one six-process summed RSS observation was approximately 507 MiB (shared pages not deduplicated, not peak). Activation with full optional-runtime verification took 9055 ms. The external test harness uses developer tools; the installed application received stripped PATH and ran bundled/verified interpreters.

Read-only `spctl --assess --type execute` rejected the private installed candidate with exit 3. Developer ID/notarization are absent. No quarantine was removed and no OS protection was disabled. Actual normal-browser download/quarantine/OS-opening acceptance is still pending; internal unquarantined build execution does not establish it.

## Optional models: separate actual evidence

The real Mac v2 capsule was freshly installed outside application resources and passed its native library self-check, including the actual final installed application menu and subsequent activation described above. Its supervised installer exited successfully with parent ownership maintained; real subprocess tests covered owner loss, time bounds, output limits and unrelated-process survival.

The installed capsule's CPU interpreter executed cached pinned Qwen and MedCPT encoders/rerankers on one disclosed public abstract, PMID 38684759. Each index/query returned three exact source candidates; observed execution was 20.73 seconds for Qwen and 13.81 seconds for MedCPT. Approved cached files were reused without model/provider downloads. These were separate capsule/engine integration checks, not model execution inside the final application UI, a benchmark, independent human support or evidence of superiority over Core. Windows optional runtime remains unavailable. New map dependencies are not bundled; saved maps remain separate.

## Actual payload inventory and remaining distribution gates

Both final payloads passed separate before/after manifest and privacy scans with zero findings for owner/build paths, common credential formats, private database/browser-state/backup/private-key/model filenames. Public CA material and upstream test/copyright markers remain legitimate retained distribution inputs. Mac: 4102 manifest entries, 83 metadata components, 498 Chromium credit sections, 17 Python provenance components, 32 native files. Windows: 7366 manifest entries, 159 metadata components after alias expansion, 500 Chromium credit sections, 16 Python provenance components, 120 native files. Both retained 64 canonical web notice packages with zero missing notice sources. MIT and third-party notices match source. Original client-only and sharp/libvips package identities are absent from the native payloads.

The SBOM includes file hashes, extensionless native-header detection, structured bundled/vendor credits and explicit unknown versions. It is not a complete static-link analysis or legal clearance. Remaining reviews concern Electron/Chromium vendor/source/codec mapping; CPython linked native-library versions/source obligations; native Python wheel/Rust transitives; and Windows pywin32/Microsoft runtime redistribution conditions. Exact retained texts and source pointers are recorded in external per-target obligation reports.

There is no installed Windows test machine and no signing identity available. Windows source/compiler policy tests are not installed Setup.exe evidence. Same-version Windows reinstall deliberately requires uninstall first; modified/unlisted files left after uninstall may require owner inspection before reinstall, rather than automatic recursive deletion.

For public Mac distribution, the owner must supply an authorized Developer ID signing/notarization setup and complete normal downloaded-artifact acceptance. Apple's program currently lists [US$99 annual membership](https://developer.apple.com/programs/). No enrollment or purchase occurred. Windows requires a suitable authorized signing method and an actual Windows 11 downloaded/installed test. [Microsoft states](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation) that signatures do not guarantee immediate SmartScreen reputation; its cited Artifact Signing option starts at US$9.99/month and requires identity/eligibility checks. No service was chosen or purchased.

One existing UI copy issue was observed and left outside this frozen packaging checkpoint: collection preparation still says a comparison uses at most 10 reports, while `MAX_BOARD_PAPERS` and the contracts allow 30. This does not change the three-report check or impose a new review-library limit.

Public native publication remains blocked by those concrete review/signing/platform gates. Old releases, their original hashes, research data and all deferred hosted work remain preserved.
