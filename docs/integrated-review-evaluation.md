# Integrated review: independent acceptance evidence

Status: the coordinator accepted the two bounded E8 integration cases after code/report review; the final clean staged regression remains the release gate. Evaluation owns `tests/test_integrated_review_acceptance.py` and this report. The frozen acceptance contract is `docs/integrated-review-milestone.md`. No operational code, bibliography/source fixtures, medical gold, settings, original user data, README or Git state was changed.

The fixtures were authored independently by Retrieval: eight distinct bibliography reports from `tests/fixtures/studies/`, five invented PubMed members and their original response bytes from `tests/fixtures/pubmed/`, and exact synthetic JATS/TXT source blocks and manual extraction truth from `tests/fixtures/evidence/`. The workflow uses temporary copied inputs and one temporary SQLite ledger. An injected client returns the fixed search and three fetch responses; network connections and sleeps are denied in the test process. The two actual retrieval CLI subprocesses use offline environment settings and no credentials.

## One complete review

The first case imports the eight bibliography rows twice under distinct exact query/date/filter/path/hash metadata. The first keyed replay changes no SQLite rows. It then captures/imports the five PubMed records through the injectable client, preserving the complete receipt and six raw/combined/receipt artifacts. The independent expected totals are:

| Quantity | Expected and observed |
| --- | ---: |
| Historical search runs | 3 |
| Identified occurrences | 21 |
| Removed duplicates | 8 |
| Canonical records | 13 |
| Awaiting title/abstract screening | 1 |
| Screened records | 12 |
| Title/abstract exclusions | 5 |
| Reports sought, retrieved and assessed | 7 each |
| Full-text inclusions / exclusions | 6 / 1 |
| Included reports with resolved study links | 6 |
| Distinct included studies | 3 |
| Study inventory / retained linkage events | 5 / 10 |
| Source versions / canonical blocks | 4 / 16 |
| Stable evidence items | 3 |
| Retained evidence revisions / review events | 5 / 5 |
| Current independently confirmed rows | 3 |
| Reconciliation checks passing | 8 / 8 |
| Export files, including durable assets | 29 |

The test compares the complete literal count dictionary, including every pending/unresolved field and all eight individual identities. It independently partitions exported records by screening/retrieval states and resolves included studies from eligible report associations. Report r3 retains two studies; r1/r2/r8 share Study A; excluded r6 retains Study D without adding it to included-study counts; unused Study E remains inventory. All ten linkage events are checked against the independent fixture's ordered report/study/reviewer/reason/kind truth.

JATS v1 attaches to r1, TXT v1 attaches separately to r2 and pending r7, and r1 later receives JATS v2. The six-week finding and explicit arbitrary appraisal for r1/Study A and the unmeasured-sensitivity negation for r2/Study A are entered and independently confirmed. Replacing r1's source suppresses the first two verified rows as stale while retaining the unaffected r2 confirmation. Complete finding/appraisal replacements use the v2 source; the finding becomes eight weeks with matching context, and distinct manual confirmation restores the two current rows. Both old revisions, their confirmations and the exact old source bytes remain in the audit export. The appraisal is a declared software fixture judgment, not a clinical quality assessment.

The export checks exact search metadata, occurrence order and original raw rows; ordered PubMed membership/receipt; all source bytes, typed blocks, source/block/revision hashes and quotation slices; current eligibility/study dependencies; exact current finding/appraisal/negation values; verified JSON and CSV structured/scalar fields; retained revision/review CSV IDs and values; flattened counts JSON/CSV; and the five title/abstract plus one full-text exclusion reasons. Hashes and quotation locations are recomputed independently rather than accepted only from a store helper.

API and actual fresh CLI retrieval traces agree. Included scope selects only active r1/v2 and r2 documents; `all_attached` additionally selects pending r7. Selected document versions, original source/block hashes, parser metadata, source identifiers and declared provenance are checked against the fixture/attachment truth. Every candidate carries matching project/report/document/version/hashes/study metadata and an exact source substring with the original typed locator. Replaced r1/v1 never appears. Complete SQLite dump fingerprints prove retrieval and export create no new events or other rows. These assertions concern structural scope and provenance, not medical retrieval quality.

After deleting every copied bibliography/source input and the original capture directory, reopening the database reproduces both retrieval traces and all 29 export files byte-for-byte. The exported capture verifies with unchanged receipt and the independently ordered five PMIDs. Reimporting that relocated capture using its original key returns the original import result without adding history, occurrences, counts or other SQLite rows; another export remains byte-identical.

## Actual concurrent snapshot

The second case explicitly enables and asserts SQLite WAL mode. During the exporter’s outer read transaction, a separate writer commits five kinds of change after the reader captures records: an additional eight-occurrence duplicate search run, a full-text exclusion, a complete study-association revision, a third r1 source version, and a complete r2 evidence revision plus confirmation.

All 29 files produced by the reader match the prior export bytes exactly, including counts, bibliography/search history, screening, study events, source metadata/blocks/assets, and evidence revisions/reviews/verified rows. The next read sees the committed state: four search runs, 29 identified occurrences, 16 duplicates, 13 records, five included reports, five source versions, six evidence revisions and six reviews. Only r2's new confirmation remains verified, and reconciliation still passes. This demonstrates a genuine SQLite snapshot across the integrated export, using a deterministic second writer rather than timing assumptions.

## Commands, corrections and limits

```text
.venv/bin/python -m pytest tests/test_integrated_review_acceptance.py -q
2 passed in 0.55s
```

The first run passed the snapshot case and failed the workflow at Evaluation's capture-artifact lookup: its helper enumerated only top-level files and omitted `batches/0001.xml` and sibling paths. Evaluation reported that wiring error before changing the helper to recursive relative paths, retaining all exact-byte/hash assertions. Inspection also corrected an unused return-key assumption before reaching replay: ordered verified membership is `receipt.pmids`, not a top-level `ordered_pmids`. Both complete cases then passed in 0.59s.

Final review strengthened the same workflow's CSV and retrieval-provenance checks. The expanded CSV assertion initially attempted JSON decoding of the arbitrary appraisal's plain scalar value; that evaluator decoder error was reported and corrected to compare the literal scalar while decoding structured finding values/context/anchors. The final unchanged two-case scope passes as recorded above. No operational defect, Implementation ticket, relaxed fixture truth or acceptance condition was required. Tests are frozen for coordinator review. No shared full regression was run; the coordinator owns the clean staged gate.

This integrated software proof uses invented records and fixed offline responses; it does not establish live PubMed completeness, clinical entailment, authenticated reviewer independence, automated appraisal, or medical retrieval quality. Source and revision digests protect against inconsistent unsigned-data changes; consistently rewriting a ledger and all hashes is outside the integrity guarantee. Existing separate legacy compatibility gates remain applicable. The v1 held-out medical retrieval quality gate remains failed and unchanged; E8 does not replace or relax it.

## Coordinator release check

Root reviewed the code and independent evaluation evidence, then tested a temporary checkout containing only the staged release files. Both licensed-source verifiers and both frozen question/anchor verifiers passed. With AGNES, NCBI and OpenAI credentials absent and model downloads disabled, the complete suite passed **1,121 tests, five existing PyMuPDF SWIG warnings, in 75.56 seconds**. No medical ranking was rerun. This release accepts the core review workflow and operational passage interfaces; both medical retrieval quality failures remain unaccepted and preserved. Unrelated local benchmark files were excluded from this release rather than subtracted from its test result.
