# Usability consolidation — evaluation and delivery

Baseline: `codex/mvp-v0-3` at `f2e1e4d2fcff5ceeb0b45b14a3ab1e4d8598de65`.
Local date: 23 October 2026. See the [guide](usability_consolidation.md) and
[implementation plan](usability_consolidation_plan.md).

## Status

All nine requested implementation outcomes are present. Fresh software checks
passed; browser coverage and its remaining gaps are distinguished below.
Evaluation ran locally before source release. The authorized source release is
limited to `codex/mvp-v0-3`; no merge, deployment, private-data publication or paid
inference was performed. Main remains `a506ae05fc19c21a1d80beabc26bfc831582441d`.

| Evidence class | Actual status |
| --- | --- |
| Engine/MVP | 730 passed; includes available Streamlit checks |
| API | 214 passed; populated capacity is reported separately |
| Populated 30 × 6 capacity | 1 passed; 153.57 seconds |
| Frontend | 149 passed after the final retry correction |
| TypeScript and production build | PASS |
| Fresh final test failures / skips | 0 / 0 |
| Live PubMed | NOT_RUN in this checkpoint |
| Real planner/proposal model calls | NOT_RUN; disabled in isolated QA |
| New embedding computation | NOT_RUN; existing saved map reused |
| Human usefulness / scientific support validation | NOT_RUN |

Total: **1,094 passed tests**, without double-counting earlier targeted runs.
The API suite emitted two inherited TestClient deprecation warnings.

## Reproduced causes and fixes

- In the frozen baseline, adding an incomplete planner concept then clicking
  Import or Browse stayed in place. A global flusher rejected every unsaved
  planner edit, and the error appeared away from the clicked button. Bounded
  incomplete editor drafts now save independently of executable plan revisions.
- Router failures previously resolved without an observable blocked outcome.
  Navigation now reports success/blocked, preserves the page, and offers recovery.
  Back/Forward uses retained history positions rather than silently replacing a
  failed destination with a success-shaped transition.
- The first browser focus check failed: a successful result was focused, then
  the route loader set that same result to null, unmounting its heading after
  the one-shot intent had been consumed. Keeping a matching result mounted fixed
  it. A fresh-build browser check observed active H2 `Search preview` at about
  47.87 CSS pixels from the viewport top.
- Adversarial review caught a current planner buffer replacing fields in a
  historical revision. Historical views now display their exact immutable draft;
  the unfinished current buffer remains separately recoverable.
- A final CAS review found that a ready, clean draft could adopt a newer server
  version while retaining stale data during Retry. Clean participants now adopt
  both current data and version; dirty conflicting drafts remain protected. The
  regression refreshes saved A to saved B, then edits one field and verifies that
  the other saved B field survives.
- Preparation and board setup previously consulted mutable/latest state and
  preselected three papers. A bounded CAS handoff captures ordered IDs, origin,
  question and expected source revision before submission, then binds the exact
  acknowledged preparation. Setup preselects all acknowledged papers.
- Import identifier, file and review state could disappear on pane changes.
  Typed input now persists; transient file/review/combination edits have explicit
  app-route and native-unload guards. Confirmed leave cannot persist a File object.

## Browser evidence — actual observations

All browser mutations used separate public-only QA stores, never the original
research database. Source snippets and entered answers were labeled software
walkthrough data; no software action constituted a research judgment.

1. Frozen baseline: reproduced blocked Import and Browse with an unfinished
   concept and blank label.
2. Updated A: dirty/incomplete planner → Import → Browse → Back → reload →
   Search restored the blank label. Three selected papers plus a filter leaving
   one visible produced identical `3 / 30 selected · 2 outside` summaries in the
   list, map and inspector.
3. Search result focus passed after the matching-result unmount fix. The
   saved 30-paper semantic artifact loaded without an embedding/model call.
4. Search path: selected 30 public papers, prepared the exact captured set,
   observed all 30 prechecked in setup, created six fields and 180 cells. DOM
   count was 180 cell buttons and one editor. Wide columns were approximately
   428 / 524 CSS pixels in that viewport.
5. Complete cell: Find relevant passages → Read in source (source heading
   focused) → explicit inspected/reference attachment → manual value and reason
   → save acknowledgment → table `1 / 180` → Edit saved cell → Save revision →
   reload retained the exact revised reason. Human support remained unassessed.
6. Clicked both CSV and audit JSON exports; API logs confirmed 200 responses
   bound to the displayed definition revision.
7. Chrome manual-intake path: identifiers survived pane switching and reload.
   Bare numbers were honestly rejected as inferred PMIDs; explicit manual
   metadata edits produced three ready records without provider resolution.
   A deliberately reviewed collection contained two public abstract excerpts
   and one explicitly synthetic unavailable citation. Setup retained all three,
   labeled Abstract only / Abstract only / Unavailable.
8. Abstract-only cell: browsed the exact retained excerpt, marked inspection
   without attaching a reference, recorded null/missing information and saved
   `not_found_in_inspected_material`. The full-paper absence caveat remained.
   The unavailable citation disabled retrieval/inspection and saved a separate
   null with an explicit missing-source explanation. Neither became supported.
9. Passage search: observed `7 requested · 2 returned`, changed the next control
   to 30 while the old run stayed seven, explicitly searched, then observed
   `30 requested · 2 returned`. No padding or automatic model call occurred.
10. Actual two-tab conflicts in both IAB and Chrome kept local tab-B text,
    blocked navigation visibly, and exercised Retry and Stay without overwriting
    tab A. Native-confirm acceptance was not reliably observable; see gaps below.
11. Responsive recovery in a fresh Chrome tab succeeded: at 390 × 844, the board
    used one 342-pixel column with no document overflow. Map/Papers keyboard
    switching and PageDown worked; tabs pinned at top 0 with height 72, and each
    visible heading pinned at top 72. The viewport was reset to 1710 pixels.
    Desktop paper-panel scrollTop reached 724 while its heading stayed at the
    panel top (52.23 CSS pixels), confirming the real nested scroll container.

Screenshots are local ignored evidence, not public research exports:
`comparison-browser.png` and `mobile-selection-browser.png` under the evidence
folder. The comparison screenshot shows the smaller abstract/unavailable QA
board, not the separate 180-cell capacity case.

### Browser gaps and tool failures

- Chrome file upload was blocked by the extension's file-URL permission. No
  browser permission was expanded. CSV/RIS behavior is covered by offline tests;
  the final browser import used manual metadata instead of claiming an upload.
- Native confirmation handling timed out in the automation bridge in IAB and
  Chrome. Retry/Stay and conflict retention were observed; explicit restore and
  beforeunload behavior passed software checks, but end-to-end confirmation
  acceptance/decline is **not browser-validated**.
- The first responsive control attempt timed out and reset browser automation.
  A fresh documented tab recovered; the later 390-pixel checks above passed.
  Actual 200% browser zoom remains **NOT_RUN**. Narrow CSS viewport checks do not
  substitute for browser/text zoom. A complete keyboard-only journey and live
  zero/error search UI are also not claimed from the partial browser checks.

## Populated capacity and retrieval evidence

The independent capacity test used 30 actual retained offline full-text sources
and populated every field with synthetic, explicitly unassessed review data:
180 initial submissions plus 180 revisions, 360 immutable cell rows and 361
idempotency rows. It reopened all 180 current cells exactly and checked exports,
historical definitions, old ten-paper v1 reads, 31-paper/7-field rejection, and
atomic byte/request-quota rollback.

Representative values were about 330 characters with one exact reference and
one inspected range of at most 256 characters per cell. Measured storage quota
usage was **2,392,079 / 33,554,432 bytes**; largest request 1,482 bytes; board view
476,844 bytes; history JSON 2,049,060 bytes; CSV 589,893 bytes. This does not claim
that all maximum-length values and all 50 revisions fit simultaneously.

The independent real-source passage smoke requested 5, 17, 10, 20 and 30 against
one retained 30-source preparation: each returned the requested number, with
480 matched / 1,725 indexed. Anchors were exact and unique; the first five stayed
unchanged; reads/replay did not retrieve again; invalid 31 and a reused request ID
with changed count rolled back. Separate tests cover every integer 1–30, fewer
and zero matches, raw legacy-run preservation and unchanged proposal budgets.
This is mechanical retrieval correctness, not relevance/recall or support quality.

## Fresh commands and results

Python commands ran from the repository; frontend commands ran from `apps/web`.
Production builds ran from the same isolated copy for the baseline and final
state, avoiding the original running application's `.next` directory. The commands
below use portable variables for machine-specific paths: `LRE_MVP_TEST_PYTHON`
and `LRE_CAPACITY_TEST_PYTHON` identify the existing test-environment binaries;
`LRE_NODE` identifies the pinned Node binary and `LRE_NODE_DIR` its directory.
Exact executed commands and paths remain in the ignored local verification logs.

### MVP

```sh
env -u NCBI_EMAIL -u NCBI_API_KEY -u AGNES_API_KEY -u DEEPINFRA_API_KEY MVP_PROPOSALS_ENABLED=0 MVP_SEARCH_PLANNER_ENABLED=0 MVP_MAP_ENABLED=0 "$LRE_MVP_TEST_PYTHON" -m pytest tests/mvp -q
```

Result: **730 passed, 0 failed, 0 skipped** (37.66 seconds).

### web API excluding separately fresh populated capacity

```sh
env -u NCBI_EMAIL -u NCBI_API_KEY -u AGNES_API_KEY -u DEEPINFRA_API_KEY MVP_PROPOSALS_ENABLED=0 MVP_SEARCH_PLANNER_ENABLED=0 MVP_MAP_ENABLED=0 .venv-map/bin/python -m pytest tests/web_api --ignore=tests/web_api/test_usability_capacity_independent.py -q
```

Result: **214 passed, 0 failed, 0 skipped** (73.92 seconds).

### populated capacity

```sh
LRE_USABILITY_CAPACITY_REPORT=.mvp-web-state/ui-checks/usability-2026-10-23/b-capacity-report.json "$LRE_CAPACITY_TEST_PYTHON" -m pytest tests/web_api/test_usability_capacity_independent.py -q
```

Result: **1 passed, 0 failed, 0 skipped** (153.57 seconds).

### frontend

```sh
"$LRE_NODE" --import tsx --test tests/*.test.ts tests/*.test.tsx
```

Result: **149 passed, 0 failed, 0 skipped** (3.421 seconds).

### TypeScript

```sh
"$LRE_NODE" node_modules/typescript/bin/tsc --noEmit --incremental false
```

Result: **PASS**.

### production build

```sh
NEXT_TELEMETRY_DISABLED=1 PATH="$LRE_NODE_DIR:$PATH" "$LRE_NODE" node_modules/next/dist/bin/next build
```

Result: **PASS**.

Additional checks: `git diff --check` passed; the generated OpenAPI JSON equaled
fresh `create_app(temporary_directory).openapi()` exactly; API types regenerated
with the existing `openapi-typescript` CLI. Export now preserves declaration
order, reducing unrelated generated-file reorder noise to a small semantic diff.

Intermediate evidence is retained honestly: an early isolated build omitted the
shared theme and was repaired before passing; one environment lacked optional
Streamlit testing (four skips), while the final complete MVP environment ran all
730 without skips. Earlier frontend failures after intended label/default changes
were updated to assert the new explicit interactions; they are not final passes
by omission. The initial real-browser focus failure and its correction are above.

## Dependencies, payloads and build size

Same Node, dependency files, directory and telemetry settings; existing locked
packages copied because Turbopack rejected an external dependency symlink.
Package/lock hashes are unchanged: **zero new production dependencies**.

| Static assets | Before raw | After raw | Delta raw | Before gzip | After gzip | Delta gzip |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| JS (10 files) | 777,581 | 814,466 | +36,885 (+4.744%) | 228,694 | 238,638 | +9,944 (+4.348%) |
| CSS (1 file) | 12,297 | 14,157 | +1,860 | 3,349 | 3,705 | +356 |

One active editor mounts on demand. Opening 180 cells is not 180 retrievals or
model calls. Extra persisted UI data is bounded: one planner editor draft per
opened plan scope, one import intake draft per workspace, and a small immutable
capture per preparation handoff, all sharing existing draft quotas. The board
summary adds preparation/ordered-paper metadata without loading every cell.

## Preservation and start-up

The read-only preservation check at **2026-10-23 09:33:28 UTC** compared declared
primary keys and row digests against the consistent baseline backups. All
**1,317 baseline rows across 46 tables** remain unchanged: **0 removed and
0 modified**. All **148 unrelated files**, branch, HEAD and main also remain
unchanged.

The current databases contain **65 additional rows**:

| Database | Added rows by table |
| --- | --- |
| `paper-maps.sqlite3` | `paper_embeddings`: 30; `paper_map_vectors`: 30; `paper_maps`: 1 |
| `web-credentials.sqlite3` | `web_create_requests`: 1; `web_workspaces`: 1 |
| `workspaces.sqlite3` | `mvp_requests`: 1; `mvp_workspaces`: 1 |
| `evidence-boards.sqlite3` | 0 |

Those three database files now have different hashes; the board database remains
identical. The cause of the additions was not established by this audit. No
records were restored or removed. Both recorded isolated QA workspace IDs are
absent from the original workspace/credential ID columns; the IDs and detailed
audit artifacts remain local. The API process listening on 8769 holds its
preparation-worker lock in the same isolated temporary QA state directory
configured by the harness. No process credential/environment values were
printed. Row-level evidence is retained in
`preservation-primary-key-delta.json` and `qa-runtime-state-path.json` under the
ignored checkpoint evidence directory.

Public-only final QA runs at `http://127.0.0.1:3005` with API on 8769 and separate
state. It does not display the private research workspace or enable live/models.
To run current code against your existing local research store, first stop the
old launcher so it releases 3000/8765, then use the existing environment:

```sh
.venv-map/bin/python scripts/run_web.py --data-dir .mvp-web-state \
  --node "$LRE_NODE"
```

This is development mode and uses current source; the original root production
`.next` build was deliberately not replaced. Existing setup/production options
remain in `docs/mvp_v0_2.md`; its old feature counts are historical, superseded by
this guide. Reload the browser after restarting. Keep the same origin/profile
and data directory to retain authorized access. No new package install is needed
for this checkpoint in the inspected environment.

Local evidence folder: `.mvp-web-state/ui-checks/usability-2026-10-23/`, including
baseline/after preservation, exact command logs, build measurements, capacity and
passage reports, A/B/browser records and screenshots. These artifacts stay ignored.

## Exact changed file scope

The following excludes all pre-existing unrelated changes and supplied briefs:

- `apps/streamlit/app.py`
- `apps/web/app/globals.css`
- `apps/web/components/board-candidates.tsx`
- `apps/web/components/cell-proposals.tsx`
- `apps/web/components/collection-explorer.tsx`
- `apps/web/components/compare.tsx`
- `apps/web/components/discover.tsx`
- `apps/web/components/evidence.tsx`
- `apps/web/components/exploration-heading.tsx`
- `apps/web/components/exploration-panels.tsx`
- `apps/web/components/import-papers.tsx`
- `apps/web/components/intake-guard.tsx`
- `apps/web/components/map-explorer.tsx`
- `apps/web/components/preparation-jobs.tsx`
- `apps/web/components/search-planner.tsx`
- `apps/web/components/workspace-app.tsx`
- `apps/web/lib/board-drafts.tsx`
- `apps/web/lib/board-guidance.ts`
- `apps/web/lib/comparison-handoff.ts`
- `apps/web/lib/drafts.tsx`
- `apps/web/lib/generated-api.ts`
- `apps/web/lib/openapi.json`
- `apps/web/tests/board-spans.test.tsx`
- `apps/web/tests/board-workflow.test.tsx`
- `apps/web/tests/cell-proposals.test.tsx`
- `apps/web/tests/discover-import-navigation.test.tsx`
- `apps/web/tests/discover-selection.test.tsx`
- `apps/web/tests/drafts.test.tsx`
- `apps/web/tests/import-collection-fixtures.ts`
- `apps/web/tests/import-workflow.test.tsx`
- `apps/web/tests/inspector-navigation-independent.test.tsx`
- `apps/web/tests/map-navigation.test.tsx`
- `apps/web/tests/map-selection-integration.test.tsx`
- `apps/web/tests/offline-example.test.tsx`
- `apps/web/tests/origin-paper-projections.test.tsx`
- `apps/web/tests/preparation-jobs.test.tsx`
- `apps/web/tests/query-suggestions.test.tsx`
- `apps/web/tests/search-planner.test.tsx`
- `apps/web/tests/usability-discovery.test.tsx`
- `apps/web/tests/usability-draft-recovery-independent.test.tsx`
- `apps/web/tests/usability-handoff-independent.test.ts`
- `apps/web/tests/usability-import-safety.test.tsx`
- `apps/web/tests/usability-passage-count.test.tsx`
- `docs/usability_consolidation.md`
- `docs/usability_consolidation_evaluation.md`
- `docs/usability_consolidation_plan.md`
- `scripts/export_web_openapi.py`
- `src/mvp/board_contracts.py`
- `src/mvp/contracts.py`
- `src/mvp/evidence_board.py`
- `src/mvp/limits.py`
- `src/mvp/service.py`
- `src/mvp/span_board_contracts.py`
- `src/mvp/usability_draft_contracts.py`
- `src/web_api/app.py`
- `tests/mvp/test_board_limit_contracts.py`
- `tests/mvp/test_boards.py`
- `tests/mvp/test_selection_limits_independent.py`
- `tests/web_api/test_passage_limits_independent.py`
- `tests/web_api/test_selection_limits_independent.py`
- `tests/web_api/test_usability_capacity_independent.py`
- `tests/web_api/test_usability_drafts_independent.py`
- `tests/web_api/test_usability_passages_independent.py`
