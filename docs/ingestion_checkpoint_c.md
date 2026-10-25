# Checkpoint C — retained citation imports and collections

Accepted locally on 22 October 2026, continuing the uncommitted A/B work on
`codex/mvp-v0-3` at `551068a16741820fe316b5027b5b181f4e0c9770`.
Main remains `a506ae05fc19c21a1d80beabc26bfc831582441d`.
No commit, push, merge or deployment was performed.

## Implemented workflow

1. Upload Zotero CSV or compatible RIS, or paste an exact identifier list.
   Parsing is private, bounded at 500 rows/5 MiB and never opens attachments.
2. Inspect row diagnostics, edit the bibliographic mapping/metadata, and
   explicitly resolve at most three exact identifiers per request. Crossref and
   Europe PMC are fixed adapters; unknown identities remain unresolved.
3. Explicitly select accepted rows and duplicate/conflict decisions. Committing
   creates an immutable citation collection, retaining pending/error accounting,
   original file/row hashes, supplied metadata and separate enrichment receipts.
4. Explore a collection, save a reviewed subset or combine saved search/import
   inputs. Saved searches have a read-only collection adapter. Imports never
   become invented PubMed searches or complete captures.
5. Prepare up to thirty selected reports through the existing durable job
   lifecycle, then retrieve passages, inspect exact sources, create a smaller
   comparison board, edit/submit/revise cells, reopen and export.

Provider-reported counts, search dates and queries are null where unknown.
Imported abstracts retain their actual origin; they are not labeled PubMed
abstracts. Raw notes/attachment columns are excluded from default projections
and exports. Original import bytes remain private, checksummed storage.

## Compatibility and boundaries

Legacy Paper, SearchPreview, preparation, run, map and board serializers retain
their original meanings. New collection-bound operations use explicit v2
contracts and real collection references. New preparations retain ordered
selected-member metadata snapshots and a checksum, so historical evidence and
boards resolve their original bibliography without a fabricated search or
UUID-only capability recovery.

The first collection preparation upgrades that workspace payload to v2 inside
the same guarded publication transaction. Before doing so it retains a
checksummed compressed copy of the exact original v1 payload. Quota, stale-job,
cancellation or SQL publication failure rolls back both source publication and
the compatibility copy. Ordinary reads/import previews do not upgrade it.
All storage remains local SQLite; no source history is discarded.

Collection preparation shares one existing worker owner, combined job quotas,
leases, cancellation, restart/staging and atomic publication. Streamlit's local
worker also registers the collection domain, avoiding a second competing owner.
Source fetching, parsing and validation occur before the short publication
mutation lock. Progress reads remain separate.

Collection maps share the pinned local title/abstract embedder, cache, geometry,
quotas and single existing map worker. Fifty papers is an explicit map maximum;
larger inputs require a saved subset. Filtering, selection and reopening do not
refit saved maps. Passage retrieval and old map artifacts remain unchanged.

Collection-aware workspace audit/export and board table/audit schemas are v2.
All-v1 exports retain their schemas. A mixed board history uses the new wrapper
even when an older v1 definition is selected. Workspace exports read research
and collection provenance from one SQLite snapshot, omit raw imports/private
fields and reject a complete export above 64 MiB rather than silently truncate.
CSV retains formula-injection protection; canonical JSON retains original values.

## Fresh software checks

| Command | Actual result |
|---|---|
| `/private/tmp/lre-mvp-venv/bin/python -m pytest tests/mvp -q -rs` | 515 passed, 0 failed/skipped, 33.65 s |
| `.venv-map/bin/python -m pytest tests/mapping tests/web_api -q -rs` | 193 passed, 0 failed/skipped, 62.82 s; two existing dependency deprecations |
| Bundled Node `node_modules/vitest/vitest.mjs run` in `apps/web` | 105 passed, 0 failed/skipped, 2.06 s |
| Bundled Node `node_modules/typescript/bin/tsc --noEmit` | Passed |
| OpenAPI generation + `openapi-typescript` | Passed; 65 API paths |
| `NEXT_TELEMETRY_DISABLED=1` bundled Node `next build` in the isolated acceptance copy | Passed, including production TypeScript/static generation |
| `git diff --check` | Passed |

Independent subsets are included in those totals, not additional denominators:
17 preparation safety/provenance tests, six collection-map tests and four HTTP
vertical workflows. Map vectors were synthetic/mocked. HTTP used two actual
retained licensed articles plus a deliberately unavailable source, tested all
nine paper/field candidate requests, exact inspection, drafts, explicit
submission, app recreation, history, authorization/deletion and exports.

Failures encountered and resolved:

- Resolver receipts initially had three identity-binding gaps: confirmation of
  every requested identifier, consistency between receipt metadata and returned
  identifiers, and rejection of additional unconfirmed identifiers. Independent
  cases exposed these; all were fixed without inventing metadata.
- A DOI URL containing a semicolon lost its suffix through a legacy normalizer.
  The new import normalizer now preserves the full DOI path; legacy behavior is
  unchanged.
- The initial archive-corruption regression returned a missing-search error
  before the original-preparation integrity check. Validation ordering was
  corrected; the original history suite and full suite pass.
- Initial HTTP fixtures omitted required missing-information reasons or declared
  inspected ranges, and requested six passages despite the preserved five cap.
  Fixtures were corrected; submission rules and limits were preserved.
- One attempted test target did not exist, so no tests ran; it was replaced with
  the actual history/service targets. An initial build tried to write Next's
  telemetry preference outside the sandbox; rebuilding with telemetry disabled
  passed. No permissions were broadened for that build.
- Browser checks found incorrect saved-search/example labels on collection map,
  evidence and comparison views. Origin-aware labels now follow the selected
  historical artifact; mixed history has a neutral retained-history label.

## Actual browser acceptance

An isolated production build on `127.0.0.1:3003`, API `127.0.0.1:8767`, used a
separate cookie and temporary public test data. The original research servers
and databases were not replaced.

- Uploaded five CSV occurrences derived from three actual public-pack citations:
  one deliberate exact duplicate and one DOI-only pending row. Reviewed the
  explicit merge choice; four accepted occurrences became three reports. Both
  merged row origins remained inspectable, and the pending row was accounted for.
- Confirmed synthetic private-note/attachment-path sentinels were absent from
  rendered projections. All three selections survived reload.
- Prepared those reports: **two retained licensed full texts and one imported
  abstract-only source**. The published preparation was source revision three;
  the earlier thirty-source preparations remained historical.
- Retrieved five lexical passages; inspected the first exact 706-codepoint quote
  at offsets 0–706 with original paper metadata and source version.
- Created a three-report × three-editable-field collection board. Retrieved
  candidates for a full-text cell, inspected the exact range, explicitly added
  inspection/reference declarations and entered a software-test value. Reload
  restored the draft before submission, without creating a cell revision.
- Explicitly submitted, revised and resubmitted that cell. Reopened the second
  revision and loaded both immutable original revisions. Human support stayed
  **Unassessed** and scope stayed **Not assessed** throughout.
- On the abstract-only report, a field had zero lexical candidates from one
  indexed block. The UI explicitly said this was not an absence finding. Submitted
  an explicit null with the full-text limitation; no whole-paper absence or
  scientific judgment was inferred.
- Downloaded actual board CSV (15,291 bytes, nine rows) and v2 audit JSON
  (52,728 bytes). The audit retained three cell revisions, two current submitted
  cells including one null, two candidate runs and the exact collection binding.
  All support states remained unassessed; private sentinels were absent.

These are software workflow checks, not a human review or usefulness evaluation.
The browser's real embedding adapter remained disabled, with that reason visible;
no map was fitted in the browser. Map execution was checked with synthetic vectors
through domain and HTTP tests. DOI enrichment, PubMed and new real embedding or
generation calls were **NOT_RUN**. The public pack is historical retained data.

Private browser receipts/screenshots/downloads and source snapshots are in the
ignored local acceptance directory, not public source control. The independent
preservation audit verified all 1,069 original database rows and 28 table hashes,
688 protected files and unchanged HEAD/main. Thirty-seven changed original paths
belong to the assigned implementation/tests; unrelated files are unchanged.

## Startup and remaining limits

Follow [local web startup](mvp_v0_3.md#run-locally), rebuild the frontend and restart
the API. Its normal lifespan starts the shared preparation and map workers.
Use the same existing data directory. Generation and new local map computation
stay opt-in; opening a collection does not download weights or initiate a fit.
The private browser harness is acceptance infrastructure, not a replacement data
directory or deployment.

Exact-identifier enrichment remains explicit and bounded, with no title guessing
or provider fallback. Identifier-only unresolved rows cannot become invented
papers. Collection lists are paginated at fifty; exploration selection/preparation
is thirty, while board and AI budgets retain their smaller existing limits.
Real provider/model behavior and researcher usefulness remain unevaluated here.
Structured search planning and versioned passage-window improvement are D and E.

## Exact changed files since checkpoint B

The list below is computed against the retained B source copy, falling back to
the inspected Git baseline for files unchanged at B. It excludes unrelated files,
private data and generated runtime caches.

```text
apps/web/app/api/v1/[...path]/route.ts
apps/web/components/collection-explorer.tsx
apps/web/components/compare.tsx
apps/web/components/discover.tsx
apps/web/components/evidence.tsx
apps/web/components/import-papers.tsx
apps/web/components/map-explorer.tsx
apps/web/components/preparation-jobs.tsx
apps/web/components/ui.tsx
apps/web/components/workspace-app.tsx
apps/web/lib/api.ts
apps/web/lib/bridge.ts
apps/web/lib/generated-api.ts
apps/web/lib/openapi.json
apps/web/lib/paper-origin.ts
apps/web/tests/api-upload.test.ts
apps/web/tests/collection-explorer.test.tsx
apps/web/tests/collection-map.test.tsx
apps/web/tests/collection-preparation.test.tsx
apps/web/tests/collection-research-fixtures.ts
apps/web/tests/discover-import-navigation.test.tsx
apps/web/tests/import-collection-fixtures.ts
apps/web/tests/import-papers.test.tsx
apps/web/tests/import-workflow.test.tsx
apps/web/tests/origin-paper-projections.test.tsx
docs/ingestion_checkpoint_c.md
docs/ingestion_rag_checkpoints.md
src/mvp/adapters/board_storage.py
src/mvp/adapters/collection_map_storage.py
src/mvp/adapters/collection_preparation_storage.py
src/mvp/adapters/collection_storage.py
src/mvp/adapters/map_storage.py
src/mvp/adapters/metadata_resolution.py
src/mvp/adapters/preparation_storage.py
src/mvp/adapters/saved_examples.py
src/mvp/adapters/storage.py
src/mvp/adapters/transport.py
src/mvp/board_contracts.py
src/mvp/collection_contracts.py
src/mvp/collection_exports.py
src/mvp/collection_map_jobs.py
src/mvp/collection_mapping.py
src/mvp/collection_preparation_contracts.py
src/mvp/collection_preparation_jobs.py
src/mvp/collections.py
src/mvp/evidence_board.py
src/mvp/import_contracts.py
src/mvp/import_parsing.py
src/mvp/limits.py
src/mvp/local_preparation.py
src/mvp/map_jobs.py
src/mvp/mapping.py
src/mvp/origin_resolver.py
src/mvp/preparation_jobs.py
src/mvp/service.py
src/mvp/workspace_versions.py
src/web_api/app.py
src/web_api/collection_map_routes.py
src/web_api/collection_preparation_routes.py
src/web_api/collection_routes.py
src/web_api/contracts.py
src/web_api/preparation_routes.py
src/web_api/projections.py
tests/mapping/test_collection_map_independent.py
tests/mvp/test_collection_boards_unit.py
tests/mvp/test_collection_preparation_independent.py
tests/mvp/test_collection_preparation_unit.py
tests/mvp/test_collections_independent.py
tests/mvp/test_import_parsers_independent.py
tests/mvp/test_import_parsing_unit.py
tests/mvp/test_metadata_resolution_unit.py
tests/web_api/test_collection_workflow_independent.py
tests/web_api/test_import_collections_independent.py
```
