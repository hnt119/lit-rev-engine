# Review ledger milestone and agent contract

Owner: coordinator. Status: cycles 1 and 2 accepted; first milestone complete. The six priorities remain the roadmap; this milestone covers projects, record imports, search history, conservative deduplication, screening, and reconciled exports. No automatic eligibility decisions, study linkage, evidence extraction, or vector-index migration in this milestone.

## Architecture and ownership

- SQLite is the source of truth for projects, imports/search runs, raw record occurrences, canonical bibliographic records, and append-only reviewer events.
- Chroma remains the passage index; this milestone does not change the existing ingestion/RAG commands or load embedding models.
- Coordinator owns this contract, `src/review/models.py`, priorities, acceptance gates, and final evidence review.
- Implementation owns `src/review/store.py`, `src/review/identity.py`, later `src/review/cli.py` and `review.py`, and implementation unit tests.
- Retrieval owns `src/review/importers.py` and importer unit tests. It investigates supported export formats and preserves identifiers and raw fields.
- Evaluation owns `tests/test_review_acceptance.py`, `tests/fixtures/review/`, and `docs/review-evaluation.md`. It supplies independent adversarial evidence and runs the full suite after each handoff.
- No agents commit, push, install packages, edit `.env`, rewrite existing data, or edit other agents' files. Report findings and proposed interface changes to the coordinator first.

## Cycle 1 interfaces (frozen)

Types are in `src/review/models.py`.

`ReviewStore(db_path)` uses standard-library SQLite. Explicit path for tests; default path is repository `data/reviews.sqlite3`. Connections must support deterministic cleanup via `close()` and context-manager methods. Enable foreign keys. Writes are transactional. IDs are UUID strings and internal timestamps are UTC ISO strings. No key/model/network initialization.

Methods and JSON-compatible return values:

- `create_project(title, review_type, question, protocol="", eligibility=None) -> dict` with `id`, supplied fields, `created_at`. `review_type` is `systematic` or `scoping`; title and question are nonempty.
- `get_project(project_id) -> dict`; `list_projects() -> list[dict]`.
- `import_records(project_id, spec: SearchRunSpec, records: list[BibliographicRecord], idempotency_key=None) -> dict` with `search_run_id`, `identified`, `new_records`, `duplicates`. Retain exact supplied search fields, every raw occurrence, mapping to canonical record IDs, and per-run counts. Store canonical payload/metadata and original raw record payloads. Runs are immutable; subsequent searches/imports append.
- `list_search_runs(project_id) -> list[dict]` including spec fields, counts and UTC `created_at`.
- `list_records(project_id) -> list[dict]` with `id`, `project_id`, bibliographic fields. Canonical metadata fills missing fields from later occurrences, never silently overwrites conflicting populated fields. Raw occurrence history retains all versions.
- `get_occurrences(project_id, record_id=None) -> list[dict]` with run ID, canonical record ID, ordinal, `record` (original bibliographic payload, including raw fields).
- `counts(project_id) -> dict` initially with `records_identified`, `duplicate_records_removed`, `unique_records`; identity: identified = duplicates + unique.

Unknown project/record IDs raise `ValueError`; record IDs from another project must be rejected. Validate the whole import before mutation; invalid records or conflicting identifiers roll back the entire run. Empty imports are valid zero-result searches. Supplied `reported_count` can exceed imported count; export it separately and never present a partial export as a complete database search.

Idempotency: without a key, each call represents a new run. With a key, an identical spec/record payload in the same project returns the original result without increasing counts; changed payload under the same key raises `ValueError`. Identical keys in different projects are independent.

Deduplication policy:

1. Normalize DOI prefixes/URL forms and case; normalize PubMed ID URL forms to digits. Reject malformed supplied DOI/PMID values.
2. Match exact DOI or PMID within one project. If identifiers point at different existing records, or a matching record has a conflicting DOI/PMID, reject the import and preserve all prior data.
3. Fallback only when BOTH records lack DOI and PMID: exact normalized title, year, and first author, all present. No fuzzy matching and no merging on title alone. Identified records with different strong identifiers remain distinct even with identical titles.
4. Keep arXiv versions/report identities distinct unless a shared strong identifier establishes the same report. Do not infer that separate reports describe independent studies.

## Retrieval/importer contract

`load_records(path, format=None) -> list[BibliographicRecord]` supports UTF-8 canonical JSON (array), RIS, and PubMed XML. Infer `.json`, `.ris`, `.xml`, or allow an explicit format. Each record carries original fields in `raw`. Invalid records raise contextual `ValueError` with record/line detail; never silently discard records or identifiers. Zero-result JSON/XML is valid. Malformed/unsupported input fails clearly. Use standard libraries; no new dependencies.

JSON fields: title, authors (array of strings), year, doi, pmid, abstract, url, source_id; arbitrary original fields are retained in raw. RIS: handle repeated AU/A1, TI/T1, AB/N2, PY/Y1, DO, UR, ER; AN is PMID only when database/source metadata explicitly says PubMed, otherwise preserve as source_id. PubMed XML: preserve nested title/abstract text, personal and collective authors, PMID, DOI, year/MedlineDate, URL. Do not process external entities or network references. Network search is a later ticket; imports must be offline.

## Cycle 2 interfaces (frozen)

- `record_decision(project_id, record_id, stage, decision, reviewer, reason="") -> dict` appends a reviewer event. Stages: `title_abstract`, `full_text`; decisions: `include`, `exclude`, `uncertain`. Reviewer required; exclusion reason required.
- `adjudicate(project_id, record_id, stage, decision, reviewer, reason="") -> dict` appends an explicit resolution event. Never delete prior events.
- `set_full_text_status(project_id, record_id, status, reviewer, reason="") -> dict` appends retrieval events. Status: `requested`, `retrieved`, `not_retrieved`. `not_retrieved` requires a reason. Only TA-included records can enter retrieval; full-text decisions require current `retrieved` status.
- `list_decisions(project_id, record_id=None) -> list[dict]` and retrieval history equivalent preserve all revisions and reviewer IDs.
- Current screening state: latest decision per reviewer; all agree => that decision; disagreement => conflict; no decision => pending. A later adjudication resolves prior disagreement; later reviewer events invalidate the old adjudication. Uncertain/conflict states are unresolved, not exclusions.
- Before full-text activity, TA decisions may be revised freely. Once any retrieval event exists, prevent TA changes that would invalidate TA inclusion; explain the error. This protects reconciled stage counts while retaining the audit trail. Reopening prior stages is a future explicit operation, not an implicit deletion.
- `export_project(project_id, destination) -> dict` exports deterministic JSON and CSV records, search runs, occurrences, reviewer/retrieval events, counts, and exclusion reasons. Export filenames/CLI specified in cycle 2. No study-count assertions until study linkage exists.

Counting identities (all counts scoped to project, current states derived from append-only history):

- identified = duplicates removed + unique records.
- unique = awaiting TA screening + TA screened.
- TA screened = TA excluded + TA included + TA unresolved (uncertain/conflict).
- TA included = awaiting full-text request + reports sought.
- reports sought = reports retrieved + reports not retrieved + awaiting retrieval.
- reports retrieved = awaiting full-text assessment + reports assessed.
- reports assessed = reports included + reports excluded + full-text unresolved.
- `included_studies` is null/unavailable, not assumed equal to included reports.

## Acceptance gates

Cycle 1: independent fixtures demonstrate persistence across reopen, isolation of two projects, immutable search history, raw provenance, intra/inter-run duplicates, identifier normalization, conservative fallback, conflicting-ID rollback, invalid-row rollback, zero-result runs, and explicit idempotency. Existing 69 tests remain green. No external requests or embedding-model loading.

Cycle 2: independent reviewer disagreement/revision/adjudication scenarios, full-text stage prerequisites, exclusion reasons, all counting identities including pending/unresolved states, source/run counts, CSV escaping/round-trip, unknown/cross-project ID rejection, and an end-to-end CLI workflow in a fresh directory. Exported counts must match independently computed fixture counts. README describes actual functionality and methodological limits.

Handoff format: ticket; files; changed facts/interfaces; acceptance evidence (command and result); unresolved failures. Keep handoffs concise. Coordinator decides the next ticket after evaluating evidence.

## Cycle 1 clarifications

- Reject `reported_count` smaller than supplied occurrences. Larger reported counts explicitly describe partial imports; count only actually imported occurrences in flow totals.
- Unknown query/search dates stay null; internal import timestamps do not substitute for search execution dates. Preserve valid supplied ISO date/datetime text verbatim.
- Distinct versioned arXiv source IDs/URLs override no-ID title fallback; only a shared DOI/PMID can merge those versions.

## Cycle 2 export and CLI contract

Following the accepted cycle 1 gate, Implementation owns these interfaces. Store dictionaries expose stable field names and raw occurrence provenance; no dependency on embeddings or external APIs.

### Current states and counting fields

`list_records` gains `title_abstract_state`, `full_text_status`, `full_text_state` derived at read time. Status is `not_requested` when no retrieval event exists. Screening states are `pending`, `include`, `exclude`, `uncertain`, `conflict`. No stored aggregate counts that can drift.

`list_decisions(project_id, record_id=None)` includes event `id`, record/project IDs, stage, decision, reviewer, reason, `kind` (`review` or `adjudication`), `created_at`; chronological ordering uses an internal sequence to distinguish identical timestamps. `list_retrieval_events` similarly includes status/reviewer/reason. No silent updates/deletes.

An adjudication may resolve only existing decisions; reason is required for any adjudication. It has the same enum constraints as a review decision. Later reviews invalidate it. Full-text status `retrieved` is terminal, even before a full-text decision exists. A new TA event after retrieval may be added only if its resulting current TA state remains `include`; otherwise reject transactionally. This protects stage eligibility while allowing concordant added reviews. Reopening earlier stages is outside v1.

`counts` returns:

- `records_identified`, `duplicate_records_removed`, `unique_records`.
- `records_awaiting_screening`, `records_screened`, `records_excluded`, `records_included_for_full_text`, `records_screening_unresolved`.
- `reports_awaiting_request`, `reports_sought_for_retrieval`, `reports_retrieved`, `reports_not_retrieved`, `reports_awaiting_retrieval`.
- `reports_awaiting_assessment`, `reports_assessed`, `reports_included`, `reports_excluded`, `reports_assessment_unresolved`.
- `included_studies`: null, `study_linkage_available`: false.
- `reconciliation`: object with the seven named identities and boolean values. `all_checks_passed` is a separate top-level boolean. Fail export with a clear error if any identity fails.

Per-run `identified`/`new_records`/`duplicates` sum to aggregate counts. Completed flow totals and pending/unresolved totals are both exported; exclusions never include conflicts/uncertainty. A zero-result search remains visible but adds zero occurrences.

### Export

`export_project(project_id, destination) -> dict` returns `directory`, `files` (list of filename strings), `counts`. Export these UTF-8 files:

- `project.json`: versioned bundle with `schema_version: 1`, project, search_runs, records, occurrences, decisions, retrieval_events, counts. Deterministic ordering and JSON serialization for unchanged ledger contents; avoid a changing export timestamp inside content.
- `records.csv`: bibliographic fields and current states. Authors serialized as JSON array so commas/semicolons do not alter authorship.
- `search_runs.csv`: metadata, exact queries/dates, counts, source checksum, reported count; nested filters encoded as JSON.
- `occurrences.csv`: run/record IDs, ordinal and original record payload as JSON.
- `decisions.csv`, `retrieval_events.csv`: all append-only events and reviewers/reasons.
- `counts.json`, `counts.csv`: aggregate and reconciliation fields, with unavailable study count represented as null/blank and a separate false availability flag.
- `exclusions.csv`: one row per current excluded record/stage, with the active reviewers' reasons or adjudication reason. Preserve all older reasons in decisions.csv.

Use Python csv.writer/DictWriter with correct quoting. Guard spreadsheet formula injection in user-authored CSV cells beginning with `=`, `+`, `-`, `@`, tab or carriage return by prefixing a single quote; JSON preserves original text, and document this escape behavior. Do not alter ordinary non-formula strings. Build files before replacing destination outputs; never erase unrelated destination files. Full directory exports do not claim a multi-file database transaction, but must use a consistent SQLite read snapshot.

### CLI

`python review.py --db PATH <command>` emits JSON results on stdout and concise errors on stderr, exits nonzero for invalid input, and imports no models. Root default DB uses repository data/reviews.sqlite3. Noninteractive subcommands:

- `create --title TITLE --type systematic|scoping --question QUESTION [--protocol TEXT] [--eligibility-json JSON]`
- `projects`
- `import PROJECT_ID FILE [--format json|ris|pubmed_xml] --source SOURCE [--query QUERY] [--searched-at ISO] [--filters-json JSON] [--notes TEXT] [--reported-count N] [--import-key KEY]`. Compute the source file checksum, retain its name/path, and do not invent missing metadata.
- `records PROJECT_ID`, `history PROJECT_ID`, `decisions PROJECT_ID` (includes screening and retrieval histories).
- `screen PROJECT_ID RECORD_ID --stage title_abstract|full_text --decision include|exclude|uncertain --reviewer NAME [--reason TEXT]`
- `adjudicate` with the same arguments, required reason.
- `fulltext PROJECT_ID RECORD_ID --status requested|retrieved|not_retrieved --reviewer NAME [--reason TEXT]`
- `counts PROJECT_ID`
- `export PROJECT_ID DIRECTORY`

Acceptance evaluates actual subprocess CLI commands in a fresh temp DB, import checksum/metadata, validation failures, all identities, deterministic exports, formula-safe CSV and unchanged legacy ingestion/RAG tests. Help text describes record/report distinction and no automatic study linkage.

## Gate decisions

Cycle 1 accepted by coordinator: 32 implementation unit tests, 48 importer unit tests, and 37 independent acceptance cases; coordinator rerun confirmed 117 milestone tests pass. Expected first import totals 8 identified / 2 duplicates / 6 unique and follow-up totals 10 / 3 / 7 match. No operational defects reported. Full-suite evidence is refreshed after every cycle; concurrent retrieval experiment files are outside this milestone's ownership.

Next highest-value step is cycle 2 screening and exports, before live database-search automation. Reconciliation keys are frozen: `identification`, `screening_progress`, `title_abstract`, `retrieval_requests`, `retrieval_progress`, `assessment_progress`, `full_text`. `reconciliation` maps these to booleans; `all_checks_passed` is a separate top-level boolean.

Implementation derives counts in a consistent SQLite read snapshot and gathers export contents in one explicit read snapshot before writing files; ordinary connection context managers do not themselves begin read transactions. Full-text status `retrieved` is terminal for v1; explicit reopening is a later operation.

Cycle 2 CSV schemas: `counts.csv` uses `metric,value`, with reconciliation entries flattened as `reconciliation.<key>`. `records.csv` includes JSON-encoded authors/raw and the three current state fields. `exclusions.csv` uses `record_id,stage,title,reason,reviewers,kind`; reviewers are a JSON array. Multiple active reasons use newline-separated reviewer/reason text. Exact original reasons remain in the event exports and JSON bundle.

## Next priority and queued tickets

Cycle 2 accepted by coordinator: 50 store/export/CLI unit tests, 48 importer unit tests, 68 independent acceptance cases, and all 69 legacy tests pass. The complete workspace rerun is 240 passed with five existing SWIG warnings (12.82 s), including five concurrent external retrieval cases outside this commit. A clean temporary checkout of the staged Git index independently passes 235 tests (13.90 s), confirming the milestone has no dependency on those concurrent files. Independent screening ground truth is 15 identified / 2 duplicates / 13 unique reports; every frozen count field and all seven identities match. Coordinator reviewed event resolution, stage guards, transactional rollback, explicit read snapshots, CSV behavior, and CLI metadata preservation. No operational defects remain in the specified gate.

Following the screening/export gate, the next milestone is reproducible PubMed search capture. R3 research is accepted; operational implementation is queued separately. A search adapter should save the submitted query, NCBI's translated query, exact parameters, search timestamps, complete PMID membership, response bytes/checksums, warnings, and completeness evidence. History-server tokens alone are not durable provenance. Keep adapter execution metadata separate from actual search filters; freeze the receipt schema before changing the ledger interface.

Initial scope is searches with at most 10,000 matches. Larger searches must fail clearly until a separately evaluated segmentation strategy exists. [NCBI's ESearch parameter reference](https://www.ncbi.nlm.nih.gov/sites/books/NBK25499/) documents the PubMed limit and pagination. Throttle requests according to [NCBI's usage policy](https://www.ncbi.nlm.nih.gov/books/NBK25497/?report=printable); never retain API keys in receipts or exports.

| Ticket | Owner | Scope / proposed files | Acceptance criterion |
| --- | --- | --- | --- |
| R4 | Retrieval | Saved synthetic ESearch/EFetch fixtures under `tests/fixtures/pubmed/`; official field mappings | Cover zero results, multiple batches, query translation, warnings, and HTTP-200 error bodies; no clinical assertions or live medical searches. |
| I3 | Implementation | PubMed adapter under `src/search/`; isolated client and receipt interfaces frozen by coordinator first | Capture membership once; fetched PMID set must equal it exactly. Fail on >10,000 matches, missing/unexpected/duplicate IDs, malformed batches, or exhausted retries. Produce saved XML and receipt only after validation. |
| E3 | Evaluation | Independent adapter acceptance tests | Reject equal-count but wrong-membership responses; verify rate limits/retries, interruption, and offline replay from saved XML. Every incomplete result is explicit and cannot enter the complete-search path. |
| I4 | Implementation, after E3 gate | CLI search command and ledger receipt/export integration | Preserve original and translated queries plus receipt provenance across reopen/export; valid zero-result searches remain visible; existing import/screening/count gates stay green. |

Only after that gate should work move to manual duplicate reconciliation/report-to-study linkage and verified extraction. No automatic clinical eligibility or synthesis is implied by discovery completeness.
