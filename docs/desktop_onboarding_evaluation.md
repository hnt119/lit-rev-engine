# Desktop onboarding candidate — fresh evaluation

Application and installer source: **`f1ac1734c829f673ce342174a069fe868dabc786`**, clean local `codex/desktop-distribution` commit. Version **0.3.0-desktop-beta.2**, build **3002**. This document is a later evaluation record; it does not change those artifact bytes. Candidates remain private and unqualified for public native distribution. The published source beta.4 and previous native candidates are unchanged.

## Exact rebuilt outputs

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Apple Silicon DMG | 169622385 | `30c08636b310f88848bf49d40eed9b6eed8b5bcb84e90fa09ef6a1e84978c0d8` |
| Windows x64 Setup.exe | 196990017 | `7ce51a2b435ebbcc0cc946cfafc844aa9c86b0694b32f6a15f73718792b56cfc` |
| Mac app file manifest | 1082893 | `6ee72875bf5148dd677cf6434d58fa016499356eb1128fc8233294d7267a987a` |

Both targets bind the same Git-verified internal engine snapshot and production web inventory. Its internal source ZIP retains the builder's beta.4 filename; it is **not** a replacement beta.4 asset or a new public source release. Mac ordinary app files total 373662959 bytes. Windows is an actual NSIS per-user installer with AMD64 application/Python payloads, not a renamed archive; its standard installer bootstrap is PE32/i386. No target Windows code ran on the Mac builder.

The first Mac build failed because the restricted build PATH omitted existing `zstd`, required for the upstream attribution archive. The failed directory/log remain preserved. A fresh retry used the already installed build tool, with no source, dependency or application-runtime PATH change. Production web compilation and both final assemblies passed. No cloud/model calls or automatic model downloads occurred.

## Fresh automated checks

- Final affected Python batch: **131 passed, no skips**, covering onboarding, existing settings/consent, board/passage flow, mocked retrieval-pack operations, native packaging, ownership/lifecycle, export safety and uninstall policy. Two existing FastAPI/Starlette deprecation warnings remain.
- Full web suite: **216 passed, no skips**, including 16 onboarding checks; TypeScript passed. React test-renderer deprecation notices remain.
- Electron security/session/native-export contracts: **23 passed, no skips**.
- Additional overlapping notice/inventory/packaging checks: **39 passed**. These are not an additional 39 unique product behaviors.
- Both complete payload inventories passed before/after audit: **4302 Mac entries**, **7566 Windows entries**. All 198 native-source-evidence files are bundled and hash verified; 64 canonical web notice packages have zero missing retained notice sources. Private/runtime-data scans reported zero findings. All 21 files in the combined artifact index were independently rehashed.

An earlier affected run had 129 passes and one skip because Node was not on the harness PATH. The existing Node toolchain resolved the skip; the final batch above includes the added notice-copy test. A mistyped test path collected no tests before the correct paths were used. Neither harness issue is represented as an application pass.

## Actual installed Mac observations

Host: **macOS 26.6.2 arm64**, Electron 45.0.0/Chromium 156.0.8078.48, bundled Node 24.22.0 and CPython 3.12.15+20261021. Application execution received system-only PATH and clean provider/hosted/model environment. The test harness uses developer tooling; this is not a fresh OS/user with developer tools physically absent.

Finder installed/replaced the app through the DMG's Applications shortcut. The mounted image was ejected before execution. Two literal drag gestures did not complete through the UI controller; the observed successful method was Finder copy/paste through the included alias, not a proven literal-drag acceptance. All 4302 installed entries matched the rebuilt manifest and strict deep ad-hoc signature checks before launch, after reinstall and after final execution/crash checks.

Fresh public-example profile:

- Welcome appeared; **Try the saved example** opened thirty retained public papers and their saved map without settings, keys, downloads or provider/model calls.
- Explicitly selected and prepared three reports, created the ordinary three-field board, retrieved Core candidates, read an exact source, explicitly used an excerpt, wrote a labeled software-practice comment, reviewed and saved it. Support remained **Unassessed**; no scientific judgment or independent human validation is claimed.
- **Help & setup → Evidence retrieval → Back to research** retained the exact cell IDs, typed draft and source reference. Missing optional libraries/weights were visible and install/runtime actions were disabled appropriately.
- Cell → scoped passage search showed a prefilled query and no selected run. Explicit retrieval returned five passages; returning a passage opened exact-source inspection without attaching it, changing the saved value or submitting a revision.
- Native Save dialogs wrote CSV and JSON. Read-only validation confirmed nine table cells, one saved head/immutable revision, all three retained source bindings, candidate/reference ranges, no SQL writes, and matching export content. Restart reopened the saved workspace and entry without Welcome interrupting.

Separate fresh setup profile:

- Sources and Retrieval offered **Set up later**. Incomplete OpenAI configuration was rejected locally. A clearly synthetic, noncredential marker was saved only to test session lifetime; no provider connection test, consent or generation action ran.
- Quitting during the AI step and reopening resumed **AI assistance**, preserved non-secret preferences and showed **NO GENERATION KEY**. The summary showed Core manual work ready, PubMed disabled, Qwen/MedCPT setup required, and unchecked AI setup required. Completing setup created no workspace.
- Reinstall/reopening with no workspaces did not repeat Welcome after completion.

Preservation/lifecycle:

- Replacement of the older private candidate preserved all **22022** stopped public-QA state files before launch. Its old three saved cell values reopened under the successor without Welcome interception. This was the isolated public QA case, not an original research database.
- Default app removal to Trash and reinstall preserved all **72** fresh-example files and **22023** then-current older-QA files unchanged. Across the intervening older-profile execution, one browser JavaScript cache file was added and 23 browser-state files changed; all engine files remained byte-identical. No equal-count claim spans application execution.
- Killing only the verified harness-owned setup-profile main exited its owned services, freed both ports, left an unrelated owned sentinel running and yielded `integrity_check = ok` on four temporary databases. No edit was in flight. Last status metadata can remain stale after SIGKILL; this does not establish interrupted-save recovery.
- One fresh Core startup observed **2350 ms** to readiness and **2688 ms** to visible window. One runtime observation summed five Electron-reported working sets to about **517 MiB**, excluding Python and without shared-page deduplication or peak measurement. The older profile with separately installed optional libraries took **13838 ms** to readiness. These are single host observations, not comparative performance benchmarks.

## Failures, NOT_RUN and concrete release gates

- **Browser-downloaded Mac acceptance: INCONCLUSIVE.** The loopback-only index and normal Save Link As/regular link actions reached the exact DMG endpoint. The supported download-event API timed out/reset its controller, and neither expected filename appeared in the default Downloads location. No completed saved-path/hash/quarantine check was obtained. The temporary server was stopped. No protected browser page or alternate security workaround was used. This was not public HTTPS delivery.
- **Mac trust: BLOCKED.** Normal `spctl --assess --type execute` rejected the final installed app. There are zero valid local signing identities; no Developer ID/notarization credentials were supplied. Ad-hoc integrity is not trusted public signing. No quarantine removal, protection change, purchase or Apple authentication occurred.
- **Windows installed execution: NOT_RUN.** No Windows machine/VM is available. Start menu launch, ordinary-user installation, native save dialogs, crash cleanup, upgrade and uninstall on Windows remain target acceptance gates. Cross-build/PE/source tests cannot clear them. Authenticode is absent; signing cannot guarantee SmartScreen reputation.
- **Fresh-user developer-tools-absent installation, literal Mac drag, quarantined/public-HTTPS opening, other Mac versions/Intel, Windows ARM: NOT_RUN/unqualified.**
- **Native failed model download: NOT_RUN.** Mocked partial-download, cancellation, hash and no-fallback tests passed; the installed UI's missing-runtime state was observed. No weight download was deliberately started or failed for this checkpoint.
- **Live PubMed, cloud generation, real generation, new neural execution and scientific/human usefulness evaluation: NOT_RUN.** Cached real model checks in the older evaluation remain historical, not tests of this candidate.

Required owner inputs are an authorized Developer ID/notarization setup, an authorized Windows signing method and an actual Windows 11 x64 test environment. Complete the matched FFmpeg source-delivery/codec conditions review and applicable Microsoft redistribution permission/terms review described in [native distribution obligations](native_distribution_obligations.md). Pinned Rust notices and the local FFmpeg source/patch ZIP are prepared; neither a license text nor an SBOM constitutes legal clearance. Optional Mac capsule v2 remains unchanged and separately qualified; Windows optional runtime remains unavailable.

## Handoff and preservation

The private review packet contains per-target manifests, SBOMs, exact hashes, build logs, observed QA results and a website handoff with native URLs explicitly `null`. Any production signing/stapling mutation requires newly measured artifacts/hashes; these private hashes cannot silently stand in for future signed bytes.

Engine docs PR [#14](https://github.com/hnt119/lit-rev-engine/pull/14) and website PR [#37](https://github.com/hnt119/hnt119.github.io/pull/37) remain open/unmerged at their reviewed heads. No branch was overwritten or website modified. Engine main, published assets, Track B, original research and paused mobile commit `7232811` were preserved. No candidate upload, source push, tag, release, website merge/deployment, model/provider spending or paid purchase occurred.
