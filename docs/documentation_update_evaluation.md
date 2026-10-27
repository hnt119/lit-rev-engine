# Public guide update — documentation evaluation

This record covers documentation for the unchanged public **Source Beta v0.3.0-beta.4**, application source `d52e5e35c80ef435abaec0c0a6f4ed236cba9356`. It does not qualify a new application, model, native installer or scientific workflow.

## Source and guide identity

- Inspected engine main: `138bfc91d85cbe45730dd439e77f518fdbfed41d` (reviewed documentation PR #13 already merged).
- Canonical revised manual: [docs/user_manual.md at d2a3c293](https://github.com/hnt119/lit-rev-engine/blob/d2a3c2930b0708968703dee5512e908b3c0ea5ee/docs/user_manual.md), SHA-256 `bfd647db82edcfeba99b3aff1eb35071e4e8e67745c599425c1ff5f2e22a7ba9`.
- The manual applies to beta.4; this editorial commit does not replace the immutable release ZIP or original release manual. The website change consumes those exact canonical bytes and records the same documentation/application identities.
- The question-evidence branch was independently reconfirmed at `ec7897f82005eba924475848164782848d8a1708`; it was not merged or edited.

## Fresh documentation checks

The README is 758 words. All 23 previous heading anchors across README, manual and index remain available. Independent checks passed for 53 relative links/fragments and 20 beta.4 source paths/fragments. The generated published-release marker block is unchanged.

`python -m pytest -q -p no:cacheprovider tests/local_distribution/test_release_links.py` passed **15 tests** using the existing Python 3.12 test environment. `python3 scripts/release_links.py --check-readme` and `git diff --check` passed. The host's default Python and bundled utility Python did not have pytest; those environment attempts did not execute the suite, and no dependency was installed to hide that limitation.

UI labels and requirements were checked against the actual released comparison, discovery/import, passage-search and board-service code. Seven critical inspected workflow/launcher files also matched the freshly downloaded beta.4 payload hashes. This is a code/documentation audit, not a new application walkthrough or participant evaluation. In particular, the guide uses:

- **Paper i of N · Field j of M** and **Draft: saved**.
- **I have read this excerpt — use it**, **Mark inspected without attaching**, **Review entry before saving**, **Save reviewed entry**, and **Saved to comparison.**
- **Edit saved cell → Save revision**; original submitted entries remain historical.
- **Download board CSV** and **Download board audit JSON**, distinct from workspace exports.
- Both **Reason** and **Missing information** for a missing answer; an explicitly inspected range for **Not found in inspected material**, and no fabricated range for an unavailable source.

## Fresh published-asset checks

All eleven existing beta.4 assets were downloaded with anonymous full HTTPS GETs, each HTTP 200 after one redirect to the release-asset host. Complete byte lengths and SHA-256 values matched the public GitHub metadata. The archive had 270 safe entries, with all 269 manifest-bound payload files verified. The internal and sidecar manifests matched. The release source/snapshot binding, original MIT license and standalone installation/Windows/manual documents matched the package. These checks did not rebuild, relabel or upload a release.

| Existing public file | Bytes | SHA-256 |
| --- | ---: | --- |
| Source ZIP | 1921710 | `6468fe22a2215ed161827f1c4397e6faf3bf6dc728df18608ada9bbbb41cc440` |
| Manifest | 42536 | `78bb38f7e8a6f5daac9b0717ea2a4007a9d88e2885d1469ac54da6256ac41c9b` |
| SHA256SUMS | 206 | `76bc22688c54a87d80078af2a64b5117daceaaddab880fec14c5c399874a9fb9` |

The initial Python HTTPS attempt failed because that interpreter lacked its local issuer trust chain. The successful retry used the macOS system HTTPS client with certificate verification enabled. No TLS or browser-security bypass was used.

## Actual rendered checks and limits

Chrome displayed the deployed project article still advertising beta.2, its older source binding, ZIP and Windows-unsupported wording. This confirmed the mismatch in the deployed page, independently of the older local portfolio checkout. The separate website PR prepares beta.4 copy and exact mirrors; it does not mean production has been updated.

GitHub rendered the new README and canonical manual at a 390 × 844 CSS-pixel viewport. The document width was 390 pixels and the article width/scroll width 324 pixels. The practical-guide link opened the exact documentation commit, and the manual contents link reached its cell-editing fragment; Tab moved onward to the next contents link. This is desktop phone-width emulation, not a physical-device test.

The unchanged README Mermaid block remained at its loading indicator during the observed diagram check. A successful GitHub diagram rendering is not claimed; the equivalent stack/role text and full architecture link remain available. Website static-export/mobile/keyboard results are recorded with that separate change set.

No new screenshots of application/research state were needed. No live paper-provider/model calls, application behavior changes, research-data movement, native packaging or private-data uploads were performed. Private native signing/notarization, redistribution and installed-Windows gates remain unchanged. No new merge, release publication or deployment is authorized by this documentation check.

## PR #14 reconciliation with newer main — 27 October 2026

The guide branch at `9a0118e4e6331aac50005ea7de0bf99724c7096c` was reconciled with actual main `0c4ee47e7dad8fcfe2525cd2b7d99e5a57984007` by an automatic merge into the feature branch, without conflicts or incorporating PR #16. Main's RAG explanation, contributor links, `AGENTS.md` and `product_design.md` are preserved byte-for-byte. The canonical manual remains SHA-256 `bfd647db82edcfeba99b3aff1eb35071e4e8e67745c599425c1ff5f2e22a7ba9`; generated source-release markers, configuration, generator, architecture and prior anchors are unchanged.

Fresh scope: **15 release-link tests passed**, generator validation and whitespace checks passed, and **83 relative links/fragments plus 23 versioned beta.4 targets/fragments** resolved. The version-target check initially could not run because this clone lacked the Git tag; fetching the existing immutable tag allowed that check to pass. Git targets reconfirmed source beta.4 at `d52e5e35c80ef435abaec0c0a6f4ed236cba9356` and native beta.2 at `f1ac1734c829f673ce342174a069fe868dabc786`; no release assets were accessed or changed. Independent read-only preservation review passed. Copilot's quota comment is **NOT_RUN**, not a review approval; no inline review requests were present.

No new application/model/provider/native, research-data, website or browser/rendering checks were performed. Existing rendered observations above retain their original scope. The release owner alone handles the PR merge; native README PR #16 remains a separate subsequent phase.
