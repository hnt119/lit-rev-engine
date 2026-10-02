# Source-anchored evidence: independent evaluation

## E6a source-document API gate

Status: accepted by the coordinator after code and independent evidence review. Evaluation owns `tests/test_review_documents_acceptance.py` and this report. No operational files, clinical gold labels, existing data, environment settings, or concurrent retrieval work were changed. Extraction proposals, verification, appraisal, and command-line interfaces are outside this source ticket.

Retrieval authored the source bytes, locators, canonical text, and quotation truth independently in `tests/fixtures/evidence/manifest.json`. Evaluation verifies those source hashes/lengths, sorted-key compact finite UTF-8 block hashes, and every literal half-open quotation slice before comparing operational results.

| Independent source | Format | Expected blocks | Truth exercised |
| --- | --- | ---: | --- |
| source-v1.txt/source-v2.txt | UTF-8/BOM text | 1 each | Exact CRLF, composed/decomposed Unicode, emoji, and 6→8 weeks source revision |
| article-v1.xml/article-v2.xml | Synthetic JATS XML | 7 each | Title/abstract/body order, nested inline concatenation, structural paths, sections, complete table/foot, reference exclusion |
| three-pages.pdf | Synthetic PDF | 3 | Actual pages 1/2/3, blank page 2, printed labels 10/12 retained as text |

All five source/block hashes and all 16 Unicode code-point quote slices match. XML tables are one block, with caption/foot paragraphs represented once and cells separated by tabs; a spanning cell remains one textual cell. `X<sub>2</sub>` becomes `X2`. XML locators identify elements, not PDF pages. PDF block text is the existing runtime's sorted extraction with no further rewriting. Runtime Python/PyMuPDF versions and all frozen parser options are retained exact metadata; generator provenance is not substituted for the effective runtime.

The 68 independent acceptance cases prove:

- Pure parsers operate on supplied bytes without source-file reads. Attachment parses, hashes, and stores one immutable snapshot even when the original path changes while parsing. Repeated bytes create distinct immutable versions; per-report sequence, active latest version, all older bytes/blocks, and source URL/version labels survive reopening and deletion of the original source file. Stored reads and exports do not reparse documents or initialize the PDF parser.
- Empty/invalid byte inputs, unsupported formats, invalid UTF-8, malformed/error/nonarticle/entity XML, corrupt/encrypted/all-blank PDF, unsafe basenames including control characters, and invalid reviewer/reason/metadata fail with no document or count side effect. Unknown/cross-project report/document/project reads or attachments preserve both projects. Existing screening/retrieval/import/count meanings remain unchanged.
- Source identifiers come only from the primary JATS `front/article-meta/article-id`; DOI/PMID normalize through accepted rules. Equivalent repeated forms are accepted, invalid/conflicting own IDs fail, and cited IDs never supply identity. TXT/PDF and identifier-free JATS retain `{}`. Attaching source identifiers cannot fill bibliography metadata or contradict a known same-type canonical report identifier. A code review also confirms the contradiction check rereads the canonical report inside `BEGIN IMMEDIATE`.
- Namespaced JATS preserves local-tag structural paths and one-based same-tag sibling indices. Reference lists and nested peer-review/editorial `sub-article` branches contribute no primary finding blocks, while source bytes remain exact.
- Tampering with an inactive version's original byte BLOB, canonical blocks, source/block hashes, or stored block JSON makes both public getters and export reject it. Every preexisting export file remains byte-identical and no staging debris remains. This tests inconsistent byte/block tampering; consistent external rewriting of all unsigned SQLite data/hashes is explicitly outside the ledger's guarantee.
- Exports retain all metadata/version-specific blocks/source bytes, exact paths and manifest hashes/lengths, safe formula-like CSV text, nested parser metadata/identifiers, unrelated annotations, and immutable JSON originals. An unchanged snapshot exports identical bytes. A deterministic WAL second writer attaches a new version after the reader captures records; the export retains the complete old metadata, active version, blocks, bytes, and counts while the next read sees the new version.
- Reconstructed old schemas reopen without document data or new count meanings and keep the generic nine-file export. A combined source/PubMed/manual-study export retains all six PubMed assets and the original receipt alongside study arrays and document artifacts. A fresh process parses TXT/JATS and reads/exports durable PDF blocks/bytes without model libraries, settings, dotenv, PDF parser import, or network.

## Actual pinned publisher JATS sources

The three acquired medical sources in `tests/fixtures/medical_sources/` are actual licensed publisher XML, not synthetic fixtures. The source manifest/README preserve author/title/license/source attribution and acquisition/hash/version caveats. Evaluation checks the exact pinned byte length/hash and own DOI, resolves every returned structural path to its original XML element, compares paragraph/title text, nearest section titles, original element IDs, and table labels, and attaches/reads the exact source. Each also rejects attachment to a different canonical DOI despite an identical bibliography title. RAPTOR's peer-review/editorial sub-article branches are excluded. No clinical finding or retrieval gold label is inferred by these checks.

| Pinned source alias | Returned primary-article blocks | Table blocks | Source identifier |
| --- | ---: | ---: | --- |
| coach | 79 | 2 | Own DOI only |
| whitehall | 88 | 4 | Own DOI only |
| raptor | 48 | 3 | Own DOI only |

These are observed parser counts, not gold medical labels. The coordinator independently parsed the same three sources and reviewed the locator/identity/transaction evidence before accepting E6a.

## Commands and observed evidence

```text
.venv/bin/python -m pytest tests/test_review_documents_acceptance.py -q
68 passed, 5 warnings in 1.34s
```

The five SWIG deprecation warnings are existing PyMuPDF-related warnings. No failed result required an operational fix or relaxed assertion; no evaluator expectation was corrected in E6a. Tests are frozen following this independent gate. The coordinator then ran the complete staged checkout with credentials absent and Hugging Face/Transformers offline: **731 passed, 5 warnings in 38.51s**. Unrelated working-tree retrieval experiments were excluded from that checkout. Scoped Git attributes preserve byte-pinned fixtures and intentional CRLF through checkout. No shared full run was executed for E6a.

Limits: source validation establishes byte identity and quotation location, not clinical entailment, extraction correctness, reviewer independence, or medical validity. PDF extraction has no OCR or password guessing. Stored source hashes are integrity checks for unsigned data. Three real sources constitute a small software pilot; later extraction/verification APIs and independently reviewed retrieval question splits require separate frozen tickets.

## E6b manual evidence and verification API gate

Status: accepted by the coordinator after reviewing the 81 independent acceptance cases, the 42 implementation cases, literal fixture truth and operational code. Evaluation owns `tests/test_review_evidence_acceptance.py` and this appended report. The frozen APIs and export contract are in `docs/evidence-milestone.md`. No operational files, pinned source fixtures, clinical gold labels, original data, settings, network, Git operations, or retrieval ranking were changed. A shared full regression is deferred until the CLI gate, as directed by the coordinator.

Retrieval authored `tests/fixtures/evidence/extractions.json` independently from the five accepted R12 source snapshots. Its nine proposals preserve literal values, complete context, quotations and typed locators: invented six-week follow-up, 24 entries explicitly distinguished from patients, the α table row/count, 7.5 units with its literal 95% interval, a negated interpretation, composed/decomposed Unicode and an emoji, unmeasured sensitivity, physical PDF page 1, and an explicitly arbitrary software appraisal instrument/version/domain/judgment. Evaluation checks exact returned payloads, canonical revision hashes, source/block hashes, API-added locators, and durable audit/verified exports. No numerical result is recomputed or medical instrument selected.

The independent suite contains **81 cases**. It includes all nine valid fixture proposals, six independently invalid version/Unicode/table/reference anchors, four valid-anchor but unsupported interpretations, and all **32 literal steps** across three separately initialized scenarios. The remaining 59 cases exercise additional validation, transaction, ownership, integrity, concurrency and compatibility boundaries.

| Independent scenario | Expected immutable revisions/reviews | Final verified rows | Truth checked at every step |
| --- | ---: | ---: | --- |
| Verification, revision and document identity | 4 / 8 | 1 | Values 6, 6, 8, 8; disagreement, adjudication, later-vote invalidation, no inherited votes; identical-byte new source identity still stale |
| Eligibility/linkage dependency restoration | 1 / 1 | 0 | Exclusion or missing association suppresses and restoration revives the same confirmation; a new source version leaves the old confirmation stale |
| Verbatim appraisal and author separation | 1 / 1 | 1 | Exact arbitrary instrument/version/domain/judgment; current author cannot review or adjudicate; no overall score |

All per-step current revision numbers, verification states, ordered dependency issues, active event IDs, immutable history lengths, complete audit arrays and verified-only JSON outputs match the fixture's literal expectations. Reopening preserves each complete final audit snapshot. The four semantic contrasts are deliberately accepted by structural quotation validation, then explicitly rejected by a distinct reviewer: negated twelve months, entries interpreted as patients, β attribution with an α quote, and invented units mislabeled as diagnostic sensitivity. No API automatically claims semantic support.

Additional independent evidence proves:

- Revision hashes cover every public revision field except the digest, using compact sorted-key finite UTF-8 JSON. Caller mutation of nested inputs or returned anchors cannot alter the stored revision. Duplicate field slots and conflicting values from two reports linked to one study remain separate and visible; screening/study counts are unchanged and values are never pooled.
- Equal-timestamp reviews are ordered by retained sequence. Latest votes preserve disagreements even with more confirmations; explicit adjudication controls only until a later review. Verification belongs to an exact current revision, the current author cannot confirm/reject/adjudicate, and a former author can independently review a new revision authored by somebody else. Old revisions cannot receive new verification.
- Current dependency issues follow the frozen order: stale_source, source_identity_conflict, ineligible_report, unresolved_linkage, study_not_linked. A JATS source attached while bibliography PMID is unknown becomes unverified after a same-DOI import enriches a conflicting canonical PMID. Existing sources, revisions and reviews remain intact; invalid writes/reviews roll back. A correct replacement source and complete new revision need a new distinct confirmation to restore verified output.
- Proposal/revision validation rejects stale or wrong sources, ineligible reports, pending/empty/conflicted/missing study associations, foreign/unknown IDs, malformed anchors, booleans/noninteger/byte-based offsets, implicit Unicode normalization, nonfinite or malformed JSON/context, blank provenance, and invalid appraisal metadata atomically. Both projects' complete audit snapshots stay unchanged on ownership failures.
- Inconsistent tampering with a current or older revision payload, a revision digest, source bytes, or canonical source blocks makes all three evidence read APIs and export reject it. Every previously exported file remains byte-identical. This does not assert tamper-proof security against a consistent rewrite of the unsigned ledger and its hashes.
- An unchanged export is byte-deterministic and includes all source versions, original nested JSON, complete revision/review history and audit rows. Formula-shaped strings are escaped in CSV while JSON originals remain exact. Proposed and rejected rows remain in audit output, and only confirmed rows with valid dependencies enter verified JSON/CSV. Unrelated directory annotations are preserved.
- Two deterministic WAL second-writer cases change a proposal or attach a source after the export reader captures records. The export retains the complete old evidence, active source, revision/review histories, verified subset and counts; the following read sees the new proposal or stale source. Code review confirms all evidence read APIs enter the same explicit snapshot and mutations recheck dependencies inside `BEGIN IMMEDIATE`.
- Reconstructed legacy schemas retain empty evidence lists, unchanged import-key behavior/counts and nine-file generic exports. A fresh subprocess completes a TXT finding, distinct confirmation and export without models, RAG settings, dotenv, PDF parsing or network.

Observed commands:

```text
.venv/bin/python -m pytest tests/test_review_evidence_acceptance.py -q
81 passed, 5 warnings in 2.70s
```

The five warnings are the existing PyMuPDF SWIG deprecations. The first run reported 59 passes and 22 fixture-driven setup failures because Evaluation referred to the R12 manifest digest as `blocks_sha256` rather than its actual `expected_blocks_sha256` key. This evaluator wiring error was reported before correction; changing that lookup preserved the exact hash assertion. The initial corrected run passed all 81 cases in 2.59s. Final code review strengthened the existing corruption cases to require rejection by the review-history API and current reads even when an older payload is corrupt; that unchanged 81-case suite passed in 2.70s as recorded above. No operational defect or relaxed acceptance assertion was found. The coordinator reviewed the literal states/exports, identifier correction, hash/anchor validation, WAL snapshot evidence and CSV behavior and accepted E6b. Tests are now frozen.

Limits: exact anchoring and human-entered confirmation do not establish clinical entailment or authenticated reviewer independence. Instrument metadata is protocol input, not validated automated appraisal. Integrity digests cover unsigned records; a consistently rewritten database is outside this guarantee. These invented scenarios are software acceptance truth, not clinical extraction gold. The separate E6c and clean staged gates are recorded below; operational medical ranking has its own gate.

## E6c source/evidence CLI gate

Status: accepted by the coordinator after reviewing the subprocess boundaries, immutable byte-read witness, real WAL snapshots, source/PDF deletion and guarded fresh process. The clean staged regression follows. Evaluation owns `tests/test_evidence_cli_acceptance.py` and this appended report. Implementation supplied the frozen nine source/evidence commands, exact wrapper keys, and 25 focused CLI cases (54 including legacy cases); Retrieval separately proved the executable guide in `docs/verified-evidence.md`. Evaluation changed no operational code, fixture bytes, medical questions, settings, data, Git state or ranking.

All **86 independent CLI cases** pass. Behavior is asserted through the actual command interface: fresh `review.py` subprocesses receive `--db` before the command, return parseable JSON stdout with empty stderr on success, and contextual nonzero stderr with empty stdout and no traceback on failure. APIs only prepare complex ownership/snapshot ledgers or inspect durable state; the combined-read and single-read probes invoke `cli.main` directly so their deterministic hooks operate inside the actual wrapper.

The complete subprocess workflow creates a review, imports records, manually creates/links a study, screens/retrieves/includes both reports, attaches exact TXT/JATS source snapshots, and enters a finding plus an arbitrary appraisal judgment. It exercises declared current-author separation, rejection/conflict/adjudication and later-vote invalidation, complete finding and appraisal revisions with no inherited votes, rejection of incomplete appraisal replacement, rejection of old-revision verification, a source replacement, and a new distinct confirmation. After deleting every original bibliography/source/payload file, the final ledger contains **2 included reports, 1 manually linked study, 3 source versions, 5 immutable evidence revisions, 8 review/adjudication events, and 2 verified current rows**. These are hand-counted workflow totals, distinct from Retrieval's separate guide example.

The workflow checks exact source filename/default and override behavior, source URL/version label, parser block truth, source/block/revision hashes, `{document, blocks}` and `{revisions, reviews}` wrappers, project/report/evidence filters, complete original histories, unchanged reconciled counts, nested audit/verified JSON and formula-safe CSV originals. Every source artifact has the expected bytes/hash/length after deletion/reopening; unchanged exports are byte-identical. Appraisal instrument/version/domain/judgment remain explicit protocol inputs, with no score or implicit medical tool choice.

Other independent cases prove:

- Both proposal and revision payload files reject missing required keys, top-level arrays/null, malformed JSON, root/nested/array duplicate object keys, nested NaN/Infinity/-Infinity/overflow numbers, unknown fields and caller identity/author/reason overrides. Revision payloads cannot replace fixed kind/report/evidence identity. Missing/unreadable/directory/invalid-UTF-8 payload files fail contextually. Every failed operation preserves complete audit snapshots of both projects.
- Sixteen ownership cases challenge unknown or foreign project/report/study/document/evidence/revision boundaries across all nine commands. Attachment source-file/parser/provenance validation rejects missing/directory/empty/invalid-UTF-8 inputs, entity XML, unsupported format, blank reviewer/reason, traversal and C1-control filenames with no ledger side effect.
- CLI exclusion and link removal/reassignment suppress verified rows; restoring the same eligibility and requested study association restores the same confirmation and active event ID without new evidence/reviews. Every intermediate verified JSON export matches the current dependency state. Invalid current-dependency verification rolls back.
- Later same-DOI bibliography PMID enrichment introduces source_identity_conflict for an already confirmed JATS source. The CLI exposes/suppresses that state, rejects new reviews/revisions against the conflicting source, and retains the original source/revision/review bytes in audit export. A correct source attachment, complete new revision and distinct confirmation restore verified output without changing earlier provenance.
- Attachment reads `Path.read_bytes` exactly once. Mutating the original path immediately after that read cannot change the attached bytes/hash/blocks, and the result remains readable after the path is deleted.
- The two combined-read wrappers retain an actual outer SQLite snapshot. In explicit WAL mode, a deterministic second writer consistently rewrites a temporary source representation between metadata/block reads, or creates/confirms a revision between history reads. The CLI returns complete old metadata/blocks or old revisions/reviews; the next subprocess sees the complete new representation. The consistent source rewrite is a concurrency witness only, not a claim of security against rewriting unsigned data and hashes.
- PDF attachment uses exact accepted bytes and physical pages 1/2/3 including blank page 2. Stored block reads remain exact after original-file deletion. A fresh guarded process reads durable PDF blocks, attaches TXT, proposes/confirms/exports evidence and deletes inputs without importing models, RAG settings, dotenv, or a PDF parser and without opening network access.

Observed final command:

```text
.venv/bin/python -m pytest tests/test_evidence_cli_acceptance.py -q
86 passed, 5 warnings in 20.14s
```

The five warnings are existing PyMuPDF SWIG deprecations. The first prepared 53-case subprocess gate passed in 11.43s. An expanded 81-case run reported 80 passes and one evaluator lookup error: it used `duplicate_records` rather than the established import result key `duplicates`. The expected one duplicate was preserved, and the corrected assertion also requires zero new canonical records. The first two concurrent-read probes then returned `database is locked` because Evaluation had omitted explicit WAL setup on those temporary databases. Both setup errors were disclosed before correction; WAL is now enabled and asserted, all old/new snapshot checks are unchanged, and no operational fix was needed. The final existing workflow also covers a complete appraisal revision. No remaining defect or relaxed acceptance assertion was found. All 86 cases are frozen.

The E6a/E6b limits continue to apply: declared names do not authenticate reviewer independence, structural quotation validation does not prove clinical support, and these invented inputs are software truth. Live acquisition, OCR, automatic appraisal, medical retrieval quality and ranking are outside this CLI gate. The executable offline guide has its own proof; Evaluation did not count that proof as independent CLI cases.

## Coordinator complete staged regression

After accepting E6b/E6c and reviewing the executed eight-block guide, the coordinator checked out only staged files into a fresh temporary directory. With credentials absent and Hugging Face/Transformers offline, the full suite passed: **965 passed, 5 existing warnings in 70.90s**. This includes all prior bibliography, PubMed, screening, study-linkage and source gates; unrelated working-tree retrieval experiments were excluded. Scoped Git attributes retain the byte-pinned medical gold JSON and original source fixtures. The medical gold verifier also passes its five-file coordinator freeze, 23 paths and 43 quotation anchors before any ranking.
