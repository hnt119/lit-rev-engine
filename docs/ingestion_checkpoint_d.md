# Checkpoint D — explicit, revision-safe PubMed search planning

Implemented locally on `codex/mvp-v0-3`, starting from `551068a16741820fe316b5027b5b181f4e0c9770`.
This extends checkpoints A–C. It does not replace discovery, passage retrieval,
the comparison board or the frozen review engine. Nothing was committed or pushed.

## Behavior and boundaries

The primary live discovery path now offers an editable intent plan. Offline
workspaces retain their saved-example opener and offer a separate, collapsible
manual planner. A researcher records concepts, requirements/preferences/exclusions,
terms, provenance, explicit AND/OR/NOT relationships, dates and sort order.
Saving creates an immutable revision and compiles locally. Approval, diagnostics,
optional local planning proposals and actual capture are separate explicit actions.
Typing and navigation do not invoke a model or PubMed.

The compiler checks Boolean guarantees, not just mentions. `women OR Asian` does
not enforce both requirements. Broad options must name and explain relaxed
requirements, and the researcher must acknowledge those exact constraints.
Separate subquestions require a recorded explanation and separate acceptance.
Ranking/screening preferences remain visible intent; this checkpoint does not
automatically rank, filter or screen papers with them.

Specialist query strings retain their exact Unicode text, whitespace and CRLF
line endings. Browser textareas display normalized newlines, while the editor
preserves the stored string through supported editing and paste operations.
Manual strategies require acknowledgment that intent, Boolean semantics and
terminology were not parsed. Structured MeSH terms are blocked because no
official server terminology registry is installed. Human approval does not
validate a MeSH descriptor or establish that a natural-language question is
semantically covered. The original question remains visible.

## Persistence, operations and interfaces

New additive tables in the existing research SQLite database retain plan heads,
immutable revisions, approval/diagnostic/proposal/execution receipts and bounded
idempotency outcomes. No saved `SearchPreview` is manufactured for a plan,
diagnostic, import or model proposal. Actual approved execution uses the existing
discovery provider and atomically saves the real preview and its planning receipt.

All routes use existing browser ownership, session, Origin and CSRF boundaries:

```text
GET      /api/v1/workspaces/{workspace}/search-plan-capabilities
GET/POST /api/v1/workspaces/{workspace}/search-plans
GET/PUT  /api/v1/workspaces/{workspace}/search-plans/{plan}
POST     /api/v1/workspaces/{workspace}/search-plans/{plan}/approve
POST     /api/v1/workspaces/{workspace}/search-plans/{plan}/diagnose
POST     /api/v1/workspaces/{workspace}/search-plans/{plan}/propose
POST     /api/v1/workspaces/{workspace}/search-plans/{plan}/execute
```

Reads and short mutations use the lifecycle guard. Provider/model calls run
outside mutation and deletion locks. Publication rechecks the current revision,
candidate digest, ownership, deletion state and exact pending request. A late
result cannot replace a newer plan or revive a deleted workspace. Interrupted
pending calls are reported as unknown/in progress and are not automatically
repeated. Unsaved UI edits block application navigation until Save or Restore;
they are local edits until explicitly saved. Concurrent changes require inspecting
the latest revision, explicitly retaining local edits against that head and saving
again. This is not an automatic merge.

Bounds: 20 plans/workspace, 40 revisions/plan, 100 receipts, 500 request records,
8 MiB planning auxiliary storage and 512 KiB/record. Planning storage counts toward
the existing 64 MiB combined workspace limit. Each pending call reserves one
future receipt and 1,052,672 bytes for its bounded receipt/outcome; completion or
failure releases the reservation. Known exhausted capacity rejects before I/O.

An explicit diagnostic uses at most two bounded ESearch calls within 12 seconds,
retains translation/warnings/errors and up to five sampled PMIDs, and can check up
to three explicitly approved known-paper identifiers. Query membership and
recovery in an exact matching retained capped preview are separate results.
Recovery uses actually retained `Paper` records, not merely ESearch identifiers.
DOIs without established PMIDs remain unresolved. Construction and researcher-
designated held-out seeds remain distinct; neither label establishes independent
human evaluation. Diagnostics do not establish relevance, recall or complete capture.

Optional planning generation is disabled by default. It uses a separate typed
planning prompt, one explicitly configured literal loopback endpoint/model/revision,
one call, 10 seconds, 24 KiB request/response bounds, zero retries and no remote or
paid fallback. Model terms remain proposed; model output cannot approve terms,
promote preferences, resolve ambiguities, replace a saved plan or execute a query.
Invalid optional configuration leaves manual editing available. Failed/interrupted
calls can have unknown usage; no successful proposal does not imply zero compute.

Legacy-only exports retain their original schemas. Collection-only exports retain
the C v2 wrappers. Projects containing plans use the new
`mvp.research-input-audit-bundle.v3` / `mvp.research-input-export.v3` wrappers,
including `mvp.search-planning-audit.v2` plan/revision/receipt/operation history.
Their CSV adds exact planning execution provenance where a passage came from an
approved capture. Raw imported files, ignored notes and attachment paths are not
projected into the audit. Existing board exports and cell schemas are unchanged.

## Evaluation evidence

Fresh software commands from the repository root:

```sh
/private/tmp/lre-mvp-venv/bin/python -m pytest tests/mvp -q -rs
# 630 passed, 0 skipped, 34.74 s
.venv-map/bin/python -m pytest tests/mapping tests/web_api -q -rs
# 204 passed, 0 skipped, 66.55 s; two existing dependency deprecations
cd apps/web
/Users/hunt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --import tsx --test tests/*.test.ts tests/*.test.tsx
# 118 passed, 0 failed/skipped, 1.924 s
```

TypeScript, production build with `NEXT_TELEMETRY_DISABLED=1`, and `git diff --check`
passed. The independent D subset comprises 80 checks: compiler 24, diagnostics 6,
service 39 and HTTP 11. Those counts are included in the broader suites, not
additional independent observations. Tests use synthetic data and mocked
transports/models. They cover wrong authority/digests, revisions, exact strategies,
Boolean weakening, malformed/bound outputs, disabled/invalid configuration,
separate diagnostic/proposal/capture histories, replay, atomic rollback,
capacity admission/reservation, concurrent edits and interrupted deletion.

Initial tests exposed two production defects, both fixed: result capacity was not
reserved before a slow call; captured handles could publish during an interrupted
deletion before the research database was cleared. The lifecycle repair also
covers collection imports/resolution (four new regressions; affected domain/map
53 and HTTP 14 passed). An intermediate broad API run had one outdated audit-shape
assertion (list versus the new versioned object); it was corrected before the
204-test pass. Initial Next telemetry attempted a sandboxed Preferences write;
disabling telemetry resolved the build without widening filesystem access.
Browser locator calibration errors were corrected using scoped/role selectors.

## Actual browser checks

Executed in an isolated production UI at `http://127.0.0.1:3003`, API `8767`,
against a separate temporary directory containing the public C walkthrough.
The original research servers were not restarted and original databases were not
used for browser mutations. External credentials and proposal generation were
disabled in this acceptance harness.

- Created an explicit gut-microbiome/women/Asian-origin plan, retaining Southeast
  Asia as a screening preference. The focused candidate joined the three declared
  requirements with AND; the preference did not silently narrow the query.
- Added a broad development option; its approval stayed disabled until both exact
  relaxed requirements were acknowledged. Its deferral reason and retained
  preference are visible beside the candidate.
- Reopened the original revision read-only with its original approval intact.
- Pasted and saved an exact specialist strategy with two CRLF sequences and
  leading/trailing spaces. Visible saved provenance confirmed exact equality
  between the original, retained draft and compiled candidate.
- Reopened the same plan in a second tab. A stale save preserved local edits;
  explicit latest-revision inspection and reconciliation produced revision 5.
  Reload retained the question, exact strategy and deliberately reconciled sort.
- Confirmed disabled diagnostics, execution and local planning states. No live
  PubMed or model action was performed.
- Downloaded an actual 15,179,486-byte JSON audit: v3 wrapper, one plan, five
  revisions, two approvals, seven operation records and the same two preexisting
  saved captures. The retained strategy still contained two CRLF sequences.
  The deliberately ignored import note/path were absent.

These are software/browser checks, not a researcher usefulness study, retrieval
relevance measurement or medical validation. New live PubMed, real planning model,
fresh embeddings and human usefulness are `NOT_RUN`.

## Preservation and startup

Independent read-only audit: all 688 protected original files, all 1,069 original
rows and all 28 table hashes across four databases remain unchanged. No original
rows were appended, changed or removed. Branch/HEAD and `main` remain unchanged.
Ignored receipts, source freezes, screenshots and test downloads stay under the
private acceptance directory; they are not release data.

Final E audit correction: the 688-file count above preceded the last authorized
History export-copy edit, which is present in the final D source freeze. That
file was missing from the earlier task allowlist. E also explicitly assigns the
board API route and proposal-dispatch files. The final original-file accounting
is 40 task-owned and 685 protected files; all 685 protected hashes match the
original baseline. The final receipt retains the failed old 688-file comparison
and the approved scope correction. All 1,069 original rows, 28 table hashes and
their safety copies still match; no research data changed.

Use the existing [local startup instructions](mvp_v0_3.md#run-locally) and
[Streamlit instructions](manual_comparison_board.md). Restart the normal API and
web processes to load the new code; retain the existing data directory. The
isolated browser acceptance instance uses separate ports/data and does not replace
the research workspace. Model planning is optional and remains disabled unless
explicitly configured. Checkpoint E follows only after this checkpoint is frozen.

## Exact changed files since checkpoint C

The following list is generated against the private C source freeze. Unrelated
working files, specifications, research snapshots and private data are excluded.

<!-- checkpoint-D-file-list -->

- `apps/web/app/globals.css`
- `apps/web/components/discover.tsx`
- `apps/web/components/history.tsx`
- `apps/web/components/search-planner.tsx`
- `apps/web/components/workspace-app.tsx`
- `apps/web/lib/bridge.ts`
- `apps/web/lib/generated-api.ts`
- `apps/web/lib/openapi.json`
- `apps/web/tests/discover-selection.test.tsx`
- `apps/web/tests/import-collection-fixtures.ts`
- `apps/web/tests/inspector-navigation-independent.test.tsx`
- `apps/web/tests/map-navigation.test.tsx`
- `apps/web/tests/map-selection-integration.test.tsx`
- `apps/web/tests/offline-example.test.tsx`
- `apps/web/tests/preparation-jobs.test.tsx`
- `apps/web/tests/query-suggestions.test.tsx`
- `apps/web/tests/raw-query.test.tsx`
- `apps/web/tests/search-planner-fixtures.ts`
- `apps/web/tests/search-planner.test.tsx`
- `docs/ingestion_checkpoint_d.md`
- `docs/ingestion_rag_checkpoints.md`
- `src/mvp/adapters/search_diagnostics.py`
- `src/mvp/adapters/search_plan_storage.py`
- `src/mvp/adapters/search_planning.py`
- `src/mvp/adapters/storage.py`
- `src/mvp/collection_exports.py`
- `src/mvp/collections.py`
- `src/mvp/planning_exports.py`
- `src/mvp/search_plan_compiler.py`
- `src/mvp/search_plan_contracts.py`
- `src/mvp/search_plan_service_contracts.py`
- `src/mvp/search_plans.py`
- `src/mvp/service.py`
- `src/web_api/app.py`
- `src/web_api/collection_routes.py`
- `src/web_api/contracts.py`
- `src/web_api/search_plan_routes.py`
- `tests/mvp/test_collection_lifecycle_unit.py`
- `tests/mvp/test_search_diagnostics_independent.py`
- `tests/mvp/test_search_diagnostics_unit.py`
- `tests/mvp/test_search_plan_compiler_independent.py`
- `tests/mvp/test_search_plan_compiler_unit.py`
- `tests/mvp/test_search_plan_service_independent.py`
- `tests/mvp/test_search_planning_unit.py`
- `tests/web_api/test_search_plans_independent.py`
