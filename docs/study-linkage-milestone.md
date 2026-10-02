# Study linkage milestone: coordinator contract

Status: I5a/E5 and I5b/E5b accepted (40 API and 63 CLI independent cases); coordinator's clean staged regression passed 616 tests (five existing SWIG warnings). Manual linkage is separate from citation deduplication. Cochrane describes studies as the unit of interest and multiple reports as potentially useful sources for the same study; preserve secondary reports rather than removing them as duplicate citations. A report can also describe several studies. [Cochrane chapter 4](https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-04).

## Ownership and tickets

I5a: Implementation owns `src/review/studies.py`, necessary delegation/schema/count/export changes in `src/review/store.py` and `src/review/exporters.py`, and `tests/test_study_linkage.py`. Keep linkage logic in the new module; ReviewStore exposes the methods below. No CLI until I5b. No automatic clustering, metadata lookup, study merging/deletion, source download, extraction, or screening-policy changes.

R9: Retrieval owns independent synthetic linkage fixtures under `tests/fixtures/studies/` and later `docs/study-linkage.md`. Define truth from invented source/registry descriptions, independently of implementation. Include several reports of one study, a report covering two studies, pending/empty/conflicting links, revisions/adjudication, and an excluded report linked to an otherwise unused study. Do not assert real trial identifiers.

E5: Evaluation owns `tests/test_study_linkage_acceptance.py` and `docs/study-linkage-evaluation.md`. Verify independent report/study totals and every state transition, transaction and export invariant. Prepare after fixtures; run after implementation readiness. Coordinator reviews evidence, selects fixes, freezes I5b commands, updates README, and commits. Preserve unrelated concurrent retrieval work and user data.

## I5a interfaces

- `create_study(project_id, label, reviewer, reason, identifiers=None) -> dict`: create a stable manual study ID. Nonempty label/reviewer/reason strings required. Optional identifiers is a finite JSON object with string keys, retaining exactly supplied registry/source metadata; default `{}`. It is metadata, never automatic proof of identity. Return `id`, `project_id`, `label`, `identifiers`, `reviewer`, `reason`, `created_at`. Study metadata is immutable in this gate; duplicate labels/identifiers do not auto-merge identities. Unused study entries do not inflate included totals.
- `list_studies(project_id) -> list[dict]`: deterministic creation order, including unused entries.
- `record_study_links(project_id, record_id, study_ids, reviewer, reason) -> dict`: append a review event replacing that reviewer's complete proposed association set for this report. Input is a list of distinct nonempty study ID strings, all belonging to the same project. Empty list explicitly records no established association; it cannot certify completeness. Canonicalize nonempty sets to sorted ID order. Link any existing report before or after screening; linkage does not change eligibility or retrieval status. Require nonempty reviewer and reason for every event.
- `adjudicate_study_links(project_id, record_id, study_ids, reviewer, reason) -> dict`: append an adjudication with the same validation, requiring at least one existing linkage review event for this report. Empty set can clear an association; later review events invalidate prior adjudication. Return event fields `id`, `project_id`, `record_id`, `study_ids`, `reviewer`, `reason`, `kind` (`review` or `adjudication`), `created_at`; internal sequence orders events but is omitted publicly.
- `list_study_link_events(project_id, record_id=None) -> list[dict]`: append-only chronological history, with project/record validation.
- `list_study_links(project_id, record_id=None) -> list[dict]`: current state for every selected canonical report, in record creation order. Fields `project_id`, `record_id`, `state`, `study_ids`, `active_event_ids`. No events: `pending`, empty IDs. Latest event per reviewer with identical nonempty association sets: `linked`, that sorted set. Identical empty sets: `unlinked`, empty IDs. Disagreeing sets (including empty versus nonempty): `conflict`, empty IDs. A later adjudication supersedes existing reviews until a new review arrives. Active event IDs identify the latest votes or active adjudication. No majority-vote or union-of-conflicting-sets inference; required independent reviewer quorum remains protocol input.

Use append-only SQLite events and relational target rows with same-project foreign keys to both events and studies. All studies/targets/events writes are atomic, including late invalid targets. Existing ledgers open compatibly; immutable search/import/screening data and fingerprints remain unchanged. Read current linkage, counts, and exports within the existing explicit SQLite snapshot. No model, settings/dotenv, or network initialization.

## Counts and exports

A project opts into linkage when it has at least one study or link event. For projects with neither, preserve the existing count dictionary and nine-file generic export shape exactly (`included_studies=null`, `study_linkage_available=false`, seven reconciliation checks). Merely opening an old ledger must not change its meaning.

For a project using linkage, set `study_linkage_available=true` and add:

- `reports_included_linked`: full-text-included canonical reports whose current link state is `linked`.
- `reports_included_awaiting_linkage`: full-text-included reports whose link state is `pending` or `unlinked`.
- `reports_included_linkage_unresolved`: full-text-included reports whose link state is `conflict`.
- `linked_included_studies`: number of distinct study IDs across only current full-text-included, linked reports. It is a partial observed total when linkage is incomplete.
- `study_linkage_complete`: true exactly when every current full-text-included report is linked. Zero current inclusions is complete only for a project explicitly using linkage.
- `included_studies`: the distinct total above only when linkage is complete, otherwise null. Pending/unresolved screening still appears in its existing counters; this total describes current confirmed inclusions, not a finalized review certification.

Add `reconciliation.study_linkage`: `reports_included == reports_included_linked + reports_included_awaiting_linkage + reports_included_linkage_unresolved`. Incomplete linkage is a represented pending state, not an arithmetic failure. All existing seven identities continue unchanged. A study supported only by excluded, unresolved, or pending reports is not included. Association revisions and eligibility revisions update current totals without erasing history. Several included reports of the same study count once; a report linked to two distinct studies can add two.

When linkage is available, `project.json` adds `studies`, `study_links`, and `study_link_events`; export adds corresponding CSV files. Preserve exact JSON, formula-safe text, stable lists/order, all history, unrelated destination files, and PubMed artifact assets. `study_links.csv` carries current states and JSON-encoded ID lists; event CSV carries complete association sets and reviewer/reason/kind/time. An unchanged snapshot exports identical bytes. An export during a second writer's link revision must include one complete version of current links, events, and counts.

## Acceptance gate

Hand-compute an initial incomplete scenario and final linked scenario from synthetic fixture truth. Prove many-to-many associations, overlap count once, multi-study report count twice, unused/excluded studies not included, missing/empty/conflicting links prevent a final total, adjudication and later-vote invalidation, clearing/replacing links, full-text inclusion changes update totals, and immutable history after reopen. Reject unknown/cross-project reports and every invalid target/input/reviewer/reason without partial writes. Old generic keyed imports and counts/exports stay compatible. Verify snapshot concurrency, CSV quoting/formula safety, exact JSON provenance, determinism, and retained PubMed assets. Test accepted APIs offline with no models/dependencies. I5b adds CLI only after this gate.

Coordinator accepted E5 after reviewing the module, store/export delegations, fixture and literal expected counts/revisions. The initial six included reports partition into three linked, two awaiting linkage, and one conflict: observed distinct studies are three but the final total is null. The final six linked reports represent three studies. All 40 independent cases passed, including 14 retained events after revision probes, same-project targets, legacy generic behavior, source assets, and WAL snapshot checks. No implementation defect or evaluator expectation correction occurred.

## I5b CLI contract, queued after E5 acceptance

Implementation owns `src/review/cli.py` and `tests/test_study_cli.py`; Evaluation owns `tests/test_study_cli_acceptance.py`; Retrieval owns `docs/study-linkage.md`. Coordinator owns README and this contract.

- `study-create PROJECT_ID --label LABEL --reviewer REVIEWER --reason REASON [--identifiers-json '{}']`: return the new study object. Identifiers must be a finite JSON object with no duplicate keys (including nested objects).
- `studies PROJECT_ID`: return the stable study inventory array.
- `link-studies PROJECT_ID RECORD_ID (--study-id ID [--study-id ID ...] | --clear) --reviewer REVIEWER --reason REASON`: append the named reviewer's complete replacement set; IDs use repeatable flags, and `--clear` explicitly records an empty association. A required mutually exclusive parser group prevents accidental clearing by omission. Return the link event.
- `adjudicate-links` takes the same arguments and returns an adjudication event through the accepted API.
- `links PROJECT_ID [--record-id RECORD_ID]`: return `{"links": <current array>, "events": <history array>}` within one read snapshot. Validate project/optional record and retain exact event provenance.
- Existing `counts`/`export` expose the accepted linkage additions; generic/PubMed-only behavior remains unchanged. Keep JSON-only success stdout and contextual nonzero errors on stderr. No model, dotenv or network initialization.

The shared CLI JSON argument helper must reject duplicate object keys recursively as well as nonfinite values. This also prevents ambiguous eligibility/filter metadata in existing commands; valid prior JSON behavior remains compatible.

E5b runs exact subprocess commands from a different working directory against a temporary DB/fixtures. Prove many-to-many links, initial missing/conflicting study totals, adjudication, later review invalidation, explicit clear/replacement and independent expected final counts/CSV/JSON. Reject absent/both association modes, duplicate/unknown/cross-project IDs, blank reviewer/reason, malformed/nonobject/nonfinite/duplicate identifiers and unknown project without partial writes. Test `links` snapshot under a second writer and fresh command dependency isolation. Retrieval executes documented examples offline before the clean staged gate/commit.

Coordinator accepted all 63 independent E5b cases and Retrieval's exact ten-block CLI proof. The independent subprocess workflow reproduces literal initial/final totals and all six revision probes; input errors preserve both projects, JSON rejects recursive duplicates and overflowing nonfinite numbers, and filtered/unfiltered link/history reads stay within one WAL snapshot. Tests are frozen for the final regression and commit gate.
