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
