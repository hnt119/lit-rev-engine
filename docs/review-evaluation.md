# Independent review milestone evaluation

Evaluator: Evaluation agent. Scope: cycles 1 and 2 (projects, import provenance, conservative record deduplication, append-only screening/retrieval events, reconciled report counts, exports, and CLI). These checks use invented bibliography records and temporary SQLite databases; no existing data was changed and no external service/model was called.

## Commands and observed results

| Command | Result | Interpretation |
| --- | --- | --- |
| `.venv/bin/python -m pytest -q` before milestone implementation | 69 passed, 5 existing SWIG deprecation warnings, 7.58 s | Baseline regression evidence. |
| `.venv/bin/python -m pytest tests/test_review_acceptance.py -q` | 37 passed, 0.24 s | Independent cycle 1 public-API acceptance gate passes. |
| `.venv/bin/python -m pytest -q` after initial operational handoff | 143 passed, 5 existing SWIG deprecation warnings, 6.00 s | All then-present tests pass, including concurrent external retrieval tests. Importer owner may add further tests before final handoff. |
| Coordinator cycle 1 milestone gate | 117 passed | 32 store unit tests + 48 importer unit tests + 37 independent acceptance cases. |
| `.venv/bin/python -m pytest tests/test_review_acceptance.py tests/test_review_screening_acceptance.py tests/test_review_cli_acceptance.py -q` after cycle 2 handoff | 65 passed, 4.03 s | 37 cycle 1 cases + 20 initial screening/export cases + 8 CLI cases. |
| `.venv/bin/python -m pytest tests/test_review_screening_acceptance.py -q -k plain_multiline` | 3 passed, 20 deselected, 0.12 s | Additional CR/LF/CRLF round-trip cases pass without commas/quotes masking minimal quoting. |
| `.venv/bin/python -m pytest -q` after cycle 2 handoff | 237 passed, 5 existing SWIG warnings, 14.50 s | Evaluator full-suite rerun before the three additional newline cases. Coordinator independently confirmed 237 passed (13.89 s). |
| `.venv/bin/python -m pytest -q` final cycle 2 gate | **240 passed**, 5 existing SWIG warnings, 13.25 s | 69 legacy + 48 importer + 50 store/export/CLI unit + 68 independent acceptance + 5 concurrent external retrieval cases. |
| Coordinator `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m pytest -q` final rerun | **240 passed**, 5 existing SWIG warnings, 12.82 s | Both cycles accepted after code and independent evidence review. Five external retrieval cases remain outside milestone ownership. |
| Coordinator offline pytest in a clean temporary checkout of the staged Git index | **235 passed**, 5 existing SWIG warnings, 13.90 s | The committed milestone plus 69 legacy tests passes independently of all concurrent external retrieval experiment files. |

The first evaluation run had three expectation failures, all caused by the evaluator assuming a repeated incomplete no-ID/no-author row could safely deduplicate without an idempotency key. The frozen conservative policy requires that row to remain a new report in each run. Corrected independent expected totals are 16 identified, 9 duplicates, and 7 unique reports after an unkeyed replay of the eight-row fixture. No operational change was needed for those failures.

The first cycle 2 run had one evaluator assertion error: a CSV reason check selected a report's first title/abstract event rather than its full-text event. Filtering the independent assertion by both report ID and stage fixed that expectation. No operational change was needed; the next complete independent gate passed.

## Fixture ground truth and evidence

`tests/fixtures/review/README.md` describes the invented records and their expected identities independently of the implementation.

| Scenario | Expected | Observed |
| --- | --- | --- |
| First medical JSON import | 8 occurrences, 2 duplicates, 6 unique reports | Matches exactly. |
| Follow-up PMID duplicate plus new report | Totals 10 occurrences, 3 duplicates, 7 unique reports | Matches exactly. |
| Conflicting titles/authors/year/abstract for same identifiers | Keep first populated canonical fields; fill missing abstract/URL; retain all three original renal occurrences | Matches exactly. |
| Same title/author/year, distinct DOI values | Two reports | Matches. |
| Complete no-ID title/year/first-author pair | Merge after whitespace/case normalization | Matches. |
| Missing first author, year, or strong identifier on one side | Avoid unsafe title-only or identified/unidentified merges | Matches. |
| arXiv v1/v2 with equal bibliographic fallback fields | Remain distinct; a shared DOI can establish identity | Matches both cases. |
| Same idempotency key and exact payload | Return original result without adding a run/occurrence | Matches. |
| Same key with changed query, canonical metadata, or raw provenance | Reject and preserve the complete prior snapshot | Matches all three mutations. |
| Two projects with same bibliography and key | Independent run IDs, record IDs, and counts; reject cross-project record access | Matches. |
| Bridge DOI/PMID pointing to two existing reports or one conflicting identifier | Roll back the complete attempted run, including preceding valid new row | Matches all conflict forms. |
| Later invalid record or first-run conflicting identifiers | Retain no partial import | Matches. |
| Zero-result/partial-export search | Preserve run and reported count; import zero actual occurrences; reject reported count below occurrence count | Matches. |
| Store closed then reopened | All project, run, occurrence, canonical payload, and count data identical | Matches. |
| Mutable input/returned dictionaries changed after import | Saved search spec and raw provenance remain unchanged | Matches. |
| Unknown query/search date | Persist null without inventing database-search dates | Matches. |
| RIS/XML equivalence | Nested title/abstract, personal/collective author, year/MedlineDate survive; numeric AN becomes PMID only with explicit PubMed authority | Matches. |
| Malformed JSON/RIS/XML and identifier values | Contextual ValueError; no partial return; ENTITY declarations rejected | Matches ten cases. |
| Fresh interpreter imports and uses review modules | No torch, Chroma, sentence transformers, dotenv, API key, or network initialization | Matches. |

All count assertions independently enforce `records_identified = duplicate_records_removed + unique_records`. All stores use explicit temporary paths. The tests exercise the public interfaces and compare original data snapshots rather than table layouts.

## Cycle 2 independent evidence

The 13-report fixture has 15 imported occurrences and two duplicates across PubMed and Embase, plus a preserved zero-result search. Its expected final counts were written independently before implementation handoff:

| Stage | Independent expected partition | Observed |
| --- | --- | --- |
| Identification | 15 identified = 2 duplicates + 13 unique reports | Exact match. |
| Screening progress | 13 unique = 1 awaiting screening + 12 screened | Exact match. |
| Title/abstract | 12 screened = 2 excluded + 8 included for full text + 2 unresolved | Exact match. |
| Retrieval requests | 8 included for full text = 1 awaiting request + 7 sought | Exact match. |
| Retrieval progress | 7 sought = 5 retrieved + 1 not retrieved + 1 awaiting retrieval | Exact match. |
| Assessment progress | 5 retrieved = 1 awaiting assessment + 4 assessed | Exact match. |
| Full text | 4 assessed = 1 included report + 1 excluded report + 2 unresolved | Exact match. |
| Studies | Included studies null; linkage availability false | Exact match. |

The independent test compares every frozen count field and all 13 records' current state tuples. Per-run identified/new/duplicate counts match `(8,7,1)`, `(7,6,1)`, and `(0,0,0)` and sum to aggregate counts. Conflicts and uncertainty do not count as exclusions.

Additional cycle 2 behavior verified:

- Latest decision per reviewer determines consensus; disagreement resolves through revision or adjudication; later review events invalidate an earlier adjudication. Histories persist across reopen and eight deliberately equal-timestamp events retain append order.
- Reviewer IDs, valid enums, exclusion reasons, and every adjudication reason are required. Unknown/cross-project IDs cannot create or read events. Invalid changes preserve complete event/state/count snapshots.
- Full-text activity requires current title/abstract inclusion, assessment requires retrieved text, and retrieved status cannot be downgraded even before assessment. Concordant added title/abstract votes are allowed after retrieval, but a vote that invalidates adjudicated inclusion and recreates disagreement is rejected.
- Nine expected exports are generated from one snapshot, retain unrelated destination files, and are byte-identical across repeated exports. JSON fields match public ledger reads. CSV authors/filters/occurrence payloads round-trip through JSON fields; all flattened count/reconciliation CSV fields match, unavailable studies are blank, and the separate availability flag is false.
- Exclusions export only current reasons; superseded reasons remain in decision history. Adjudication reasons disappear from current exclusions once invalidated, with active reviewer reasons replacing them. Commas, quotes, CR, LF, and CRLF round-trip through CSV.
- Cells beginning with each of `=`, `+`, `-`, `@`, tab, and carriage return receive a leading quote in CSV; all exact original strings survive in JSON. No ordinary author names are altered.
- An intentionally unreconciled counts result causes export to fail before replacing a pre-existing output or unrelated destination file.
- **Actual read-snapshot consistency:** deterministic WAL-mode tests commit a new import from a second `ReviewStore` after the first connection captures record rows, by wrapping the public `list_records` seam. Counts and all exported collections retain the original consistent snapshot; the next read sees the additional record. No sleeps or race-dependent scheduling are used.
- Fresh-directory subprocess CLI executes create/import/history/screen/adjudicate/fulltext/counts/decisions/export commands without API keys. File SHA-256, multiline exact query, supplied timezone date text, filters, notes, reported count, and filename survive. Missing metadata stays null; zero imports persist; changed-key payload and malformed import fail without partial history. Errors are concise on stderr with clean stdout and no traceback.

## Limits and next gate

Cycles 1 and 2 are independently green. Final independent coverage is 68 cases: 37 cycle 1, 23 screening/export, and 8 CLI. Synthetic data demonstrates specified behavior; it does not estimate real-world false-positive/false-negative deduplication rates or cover every exporter dialect. No live PubMed search or other external import was attempted. Conservative deduplication intentionally leaves incomplete records separate; raw occurrences make later human reconciliation possible. Unique reports must not be presented as unique studies.

The milestone is an offline report ledger, not a complete systematic/scoping-review platform. Screening reviewer names are supplied identities, not authenticated users. Retrieved status is reviewer evidence, not a managed full-text file attachment. Exports use a consistent database snapshot and staged file replacement; the nine-file destination is not a filesystem transaction. Study linkage, appraisal, structured evidence extraction, live database searches, and real medical retrieval-quality evaluation remain later priorities. Five concurrent external retrieval tests in full-suite totals are outside this ledger evaluation ownership.
