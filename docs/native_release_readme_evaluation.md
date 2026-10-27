# Native release entry point — documentation checks

Scope: a documentation-only successor initially stacked on PR #14 at `9a0118e4e6331aac50005ea7de0bf99724c7096c`. No application, runtime, retrieval profile, source binding, research data, Track B, website or released asset is changed. The initial review observed main at `0c4ee47e7dad8fcfe2525cd2b7d99e5a57984007`; the reconciliation below incorporates the subsequently merged guide/main.

Integration preservation: main's separate “How RAG fits into the workflow” README section, contributor links, `AGENTS.md` and `product_design.md` are retained byte-for-byte in the reconciled branch. Main's README was not replaced wholesale.

## Published artifacts and guide binding

The primary action is the readable [macOS desktop beta.2 release page](https://github.com/hnt119/lit-rev-engine/releases/tag/v0.3.0-desktop-beta.2), published **2026-10-27T13:58:24Z** as a pre-release. Its exact application source is `f1ac1734c829f673ce342174a069fe868dabc786`. The Apple Silicon DMG is **169622385 bytes**, SHA-256 `30c08636b310f88848bf49d40eed9b6eed8b5bcb84e90fa09ef6a1e84978c0d8`.

The release owner recorded anonymous full GETs of all 18 assets, not metadata/HEAD-only checks; all hashes, the release manifest/checksums and source binding passed. This documentation lane reused those verified downloaded bytes without changing or re-uploading them. It did not repeat the downloads or the application tests.

Readable guide copies in `docs/releases/v0.3.0-desktop-beta.2/` are byte-identical to the published assets:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| INSTALL_MAC.md | 5559 | `bd3eb35baa29dd287d26cc6696f5a28b4bec0cda1c49477a6981f7df87e2ba70` |
| VALIDATION.md | 12918 | `ebca08ea60c7d5a9a6143c94737aeb48105dacf4270c602944a9e4c774e821cc` |

The guides preserve actual clean macOS 26.6.2 (25G83) arm64 observations, the QA-induced bytecode/seal incident and recovery, and the distinction between software qualification and scientific usefulness. The Mac application is **ad-hoc signed, unnotarized, and has no Apple Developer ID signature**. Windows native installation remains unavailable. Optional neural libraries/weights are not bundled; the separate Mac library capsule is not publicly offered.

Source beta.4 remains unchanged and available as an advanced setup-required option. `config/public_release.json`, `scripts/release_links.py` and the generated `published-release` block retain their original SOURCE-beta.4 semantics and bytes. The source version's Windows CI evidence is not presented as native installer qualification. The canonical beta.4 task guide is unchanged and labeled as the shared Core workflow, with native installation/welcome differences in the native guide.

## Fresh checks in this documentation lane

- `python -m pytest -q tests/local_distribution/test_release_links.py tests/local_distribution/test_native_release_readme.py`: **19 passed**. The existing interpreter/test environment was reused; no dependency upgrade or installation.
- `python scripts/release_links.py --check-readme`: **PASS**.
- `git diff --check`: **PASS**.
- All seven original README headings, both explicit legacy anchors and the small Mermaid block are retained; generated source-release block is byte-identical. Regeneration in a temporary fixture leaves the complete new README unchanged.
- Relative links/fragments across the README, index, architecture pointers and the two native guide copies are checked by the affected tests. Native guide SHA checks bind the readable copies to the published assets.
- New documentation contains no machine-specific private paths, credentials, research exports, cookie state or internal QA screenshots. Public source/asset identity and standard application/data-directory paths are intentional.
- Independent read-only wording/byte review: **PASS** for the scoped seven files, including explicit native trust/platform/model limits and preservation of source-release semantics. It did not rerun application tests or downloads.

## Not rerun or implied

Application builds/tests, model/provider calls, native installation, Windows execution and live PubMed: **NOT_RUN in this documentation lane**. Published qualification remains the separate version-bound record. New GitHub-rendered README narrow-screen and Mermaid rendering checks are **NOT_RUN by this lane**; unchanged Mermaid source is not proof of rendering. The release owner handles browser review. No merge into main, release mutation or portfolio change is performed by this lane.

## PR #16 reconciliation after PR #14 — 27 October 2026

After the release owner merged PR #14, actual main `3b7fad114631b379cbcd5f7a763b2837ba7b0960` was automatically merged into the native README feature branch at `b366bf097f6d11f06c4eb344b978985295d45217`, without conflicts. The canonical manual remains SHA-256 `bfd647db82edcfeba99b3aff1eb35071e4e8e67745c599425c1ff5f2e22a7ba9`. Main's RAG, guidance files and contributor links are preserved, along with all prior document anchors, the generated SOURCE-beta.4 block/configuration/generator, and the two exact published native guide copies. Git source targets remain beta.4 `d52e5e35c80ef435abaec0c0a6f4ed236cba9356` and native beta.2 `f1ac1734c829f673ce342174a069fe868dabc786`; no release assets were accessed or changed in this phase.

Fresh reconciliation checks: **19 affected tests passed**, source-release generator validation and whitespace checks passed, **93 relative links/fragments and 21 versioned beta.4 targets/fragments** resolved, and byte/hash preservation checks passed. Independent read-only preservation review passed. These checks do not add an application/platform/model run. Copilot's quota comment remains **NOT_RUN**, not a review approval; no inline review requests were present. The release owner alone handles retargeting and merging PR #16.

The release owner's earlier browser observations at predecessor `b366bf0` passed 1280px/390px readability and Download-for-macOS → Installation-guide keyboard focus. Mermaid rendering was **INCONCLUSIVE** (loading iframe/inspection timeout); unchanged source and readable plain-text architecture are not a diagram-render pass. Those predecessor observations are not silently promoted to a rendered check of this reconciled revision.

## Engine-only product release page — 28 October 2026

Base: main `bfd49c7149e5003c3facafdb8e87aaaa8501aa4c`. Reviewed README/test implementation: `48526a8f575bc1c86af6ebb31ac8f1c1a84791fa`; README SHA-256 `733f18b63b94af94643966197e369ba6f2ba2d7ce5beb9b8e78df044561ea6bd`. This later evaluation entry does not change those README bytes. Scope is the README, its existing documentation tests and this record. Main is not merged. The personal website, application, runtime, research data, Track B, mobile prototype, release tags and assets are untouched.

The README now puts its purpose, platform download table and one five-link help row first. **Download for macOS** points directly to the actual published DMG; Release notes remains a separate release-page link. Windows shows plain **Windows installer not yet published**, with a separately labeled source-setup fallback. Core, optional neural-runtime availability, explicit review, MIT/third-party boundaries and the concise ad-hoc/unnotarized notice retain their actual scope. Cherry Studio was consulted only for information hierarchy; no branding, copy, media or dependency was reused.

Fresh anonymous release inventory: **five public prereleases, fifty assets**, with an explicit empty next page. No public Windows EXE or newer Mac installer exists. Native beta.2 remains release `425523899`, source/tag `f1ac1734c829f673ce342174a069fe868dabc786`. Its direct DMG passed a full anonymous HTTPS GET: HTTP 200 after one HTTPS redirect, **169622385 bytes**, SHA-256 `30c08636b310f88848bf49d40eed9b6eed8b5bcb84e90fa09ef6a1e84978c0d8`, valid UDIF trailer rather than an HTML response. INSTALL_MAC, VALIDATION, RELEASE_NOTES, the release-asset manifest and SHA256SUMS also passed full anonymous GET/hash checks. Manifest source and checksum bindings agree. No installer was executed.

Fresh offline checks: `python -m pytest -q -p no:cacheprovider tests/local_distribution/test_release_links.py tests/local_distribution/test_native_release_readme.py` passed **19 tests** (existing test count, updated intentional assertions; final run 0.17 seconds). `python scripts/release_links.py --check-readme` and `git diff --check` passed. Independent review resolved **18 local references/fragments and 2 versioned engine references/fragments**, with zero broken targets. All eight prior headings, two explicit legacy anchors, the exact Mermaid source and generated source-release block remain intact. Configuration, generator, canonical manual and architecture bytes remain identical to the base. Readable content is **499 words**, excluding the generated source block, diagram code and URL destinations.

Actual GitHub-rendered README checks used the exact implementation commit above. At **1280 × 900**, document width was 1280 pixels and the article width 861 pixels. At **390 × 844**, document width was 390 pixels; article width, article scroll width and table width were each 324 pixels. Purpose, platform status, direct Mac action, secondary row and beta trust notice were readable without document overflow. Keyboard Tab reached **Download for macOS → Source setup → Getting started → User guide**; Enter on Getting started opened the actual rendered version-matched Mac installation guide. The direct-link destination matched the anonymously verified DMG. No README image/video elements or public screenshot assets were added. These are desktop browser and narrow-viewport observations, not physical-device or installed-app acceptance.

No application/native rebuild, model/provider call, live PubMed test, Windows execution, signing/notarization or new scientific evaluation was run. **Public-browser download → native installation acceptance remains INCOMPLETE**; anonymous asset-byte checks and a rendered README do not close that boundary. Mermaid bytes are preserved; no new diagram-render qualification is claimed. Missing public Windows publication is a separate release task and did not block this documentation improvement.
