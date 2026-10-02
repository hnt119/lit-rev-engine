# Integrated review acceptance: coordinator preparation

Status: preparation only; release E8 after source/evidence CLI and project retrieval gates. Evaluation owns `tests/test_integrated_review_acceptance.py` and `docs/integrated-review-evaluation.md`. Implementation receives only defects exposed by the gate. Use temporary files/ledger and existing independently authored software fixtures, without live searches, models, clinical gold assertions or user data.

## One review, complete provenance chain

Import the eight records from `tests/fixtures/studies/records.json` twice as distinct JSON search runs, preserving exact source hash/query/date metadata. Replaying the first keyed run is a no-op. Capture/import the independent five-PMID PubMed fixture through its injectable client, preserving the exact receipt and original responses. The initial ledger therefore has three historical runs, 21 occurrences/identified records, eight duplicates and 13 canonical records. No bibliography key overlaps between the two fixtures.

Apply the study fixture's initial and final screening/linkage actions. Exclude the five new PubMed records at title/abstract with explicit synthetic reasons. Expected review partition: 12 screened, five title/abstract exclusions, seven reports sought/retrieved/assessed, six full-text inclusions, one full-text exclusion and one record awaiting screening. Linkage must resolve the six included reports to exactly Studies A/B/C, preserving report r3's two studies, three reports sharing A, excluded Study D and unused inventory E. Final linked-included count is six, distinct included-study count three, and all eight reconciliation checks pass.

Attach copies of synthetic JATS v1 to r1, TXT v1 to r2, and a source to pending r7. Enter and independently confirm a six-week finding and arbitrary explicit appraisal for r1/Study A, plus a negation finding for r2/Study A using the accepted extraction truth. Replace r1 with JATS v2: its old finding/appraisal confirmations become stale and only the unaffected r2 finding remains verified. Submit complete finding/appraisal revisions anchored to v2, enter eight weeks and its matching context, and independently confirm both. Final evidence has three stable items, five retained revisions, five retained review events and three current verified rows. This is source-supported invented software truth, not a clinical appraisal.

## Retrieval, export and replay

Invoke project retrieval through the frozen API and CLI. Included scope sees only active attached documents for r1/r2; all_attached additionally sees pending r7. Every returned anchor equals its exact source substring, provenance hashes/locators agree, and replaced r1/v1 never appears. Candidate retrieval creates no evidence or verification events.

Export and inspect counts, bibliography occurrences/history, study association history, all source versions and exact bytes, all evidence revisions/reviews, and current verified rows. Independently recompute hashes, quote slices, eligibility/linkage dependencies, and the literal record/report/study totals; do not merely compare the exporter with another store helper. Confirm source v1 and stale revisions remain in audit files while verified files contain current v2 findings only.

Delete the original copied source files and capture directory, reopen SQLite, and reproduce every export byte and retrieval trace from retained data. Verify/replay the exported PubMed capture with the original import key: no new history/counts are added. Verify generic legacy exports remain compatible in their existing gates. Test failures must produce a bounded implementation ticket; do not relax independently frozen truth to achieve green results.
