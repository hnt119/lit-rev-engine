# Independent synthetic report-to-study linkage truth

These files describe invented bibliography records, source/registry descriptions, and review actions for software evaluation. They contain no real publications, trial registrations, medical outcomes, or clinical findings. Do not resolve or cite their DOIs or registry descriptions. A registry-like string is retained metadata, never automatic proof of identity.

`records.json` is a canonical import array of eight different reports in order r1 through r8. Each has a distinct invented DOI, so bibliography deduplication must retain all eight. Its extra `fixture` object is raw source provenance and includes a report alias, an invented source description, and source-asserted study aliases. These descriptions establish independent fixture truth; the ledger must not infer associations from them.

`manifest.json` defines study creation metadata, screening setup, initial and final append-only association events, current-state expectations, and hand-computed counts. Aliases A–E and r1–r8 are fixture names, not runtime UUIDs. Evaluation should map reports by their DOI and map studies by creation results before sending actual IDs to the frozen API. Association arrays in expected states express sets; stored nonempty ID sets sort by actual study ID, not by fixture alias. Original study metadata and bibliography `fixture` objects must survive unchanged in JSON provenance.

| Report | Invented source identity | Screening state | Initial link | Final link |
| --- | --- | --- | --- | --- |
| r1 | A primary report | Full-text included | A | A |
| r2 | A follow-up report, same cohort as r1 | Full-text included | A | A |
| r3 | One report describes distinct studies B and C | Full-text included | B and C | B and C |
| r4 | B companion report | Full-text included | Pending: no event | B |
| r5 | C secondary report | Full-text included | Conflict: scripted proposals A versus B | C by adjudication |
| r6 | D report | Full-text excluded | D | D |
| r7 | Unscreened bibliography record; no established association | Title/abstract pending | Pending: no event | Pending: no event |
| r8 | A companion report | Full-text included | Unlinked: explicit empty set | A by same-reviewer revision |

Create inventory entries A, B, C, D, E in that order. E is deliberately unused. Its formula-shaped label exercises safe CSV text while JSON must retain the exact value. Report r8 has quotes and a multiline raw source description for provenance/CSV checks.

For screening setup, include r1, r2, r3, r4, r5, r6, and r8 at title/abstract stage; record retrieved full text for those seven; include six at full-text stage and exclude r6 with its supplied reason. Leave r7 without screening/retrieval events. All scripted events have reviewer/reason values; no live lookup is needed.

The initial scenario has 8 identified and unique reports, 0 citation duplicates, 1 report awaiting screening, 7 assessed reports, and 6 included reports. Among those six inclusions, r1/r2/r3 are linked, r4/r8 await linkage, and r5 is unresolved: **6 = 3 linked + 2 awaiting + 1 unresolved**. The observed study union is **{A, B, C}**, so `linked_included_studies=3`; `included_studies=null` and `study_linkage_complete=false`. Linked r6 contributes no included D because its eligibility is excluded. Unused E contributes nothing. An incomplete linkage total still reconciles arithmetically.

Append the three final events without rewriting the seven initial events: link r4 to B, adjudicate r5 to C, and revise linker-one's empty r8 set to A. Now **6 = 6 linked + 0 awaiting + 0 unresolved**, and the union remains **{A, B, C}**. `included_studies=3` and `study_linkage_complete=true`. All 10 linkage events remain available after reopen/export. A has three included reports but counts once; r3 retains two distinct studies. D/E remain excluded from included-study totals. r7's pending screening remains visible, so this total describes current confirmed inclusions rather than certifying a finished review.

`revision_sequence_after_final` is a separate continuation of the final scenario; its probes are sequential, not independent resets. A new r5 review invalidates adjudication and exposes latest reviewer sets C versus B; re-adjudication resolves that conflict. Empty r3 replacement clears its whole B/C set; a later C-only replacement must not resurrect B by union. A full-text inclusion revision of r6 temporarily adds D (7 included reports, 4 studies); restoring exclusion removes D from the total while retaining its association and history. These probes end with 14 linkage events. E never contributes.

Expected counts are hand-computed fixture assertions, not output captured from the implementation. `common_counts` applies to the initial/final scenarios; revision probes override the indicated fields. Existing screening/retrieval reconciliation identities and the linkage partition must all remain true. Evaluation owns adversarial invalid/cross-project targets, transaction rollback, snapshot concurrency, exact export bytes, and retained PubMed assets; these files supply source truth rather than generated gold output.
