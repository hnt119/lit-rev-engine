# Manual comparison board evaluation

Date: 21 October 2026. Baseline: `60f8aa96a4e3ea6dcced805e2158bf5aeafa5923` on `codex/mvp-v0-3`. This checkpoint adds the manual board described in [the implementation plan](mvp_v0_3_board_plan.md); it does not repeat discovery, execute extraction or evaluate scientific usefulness.

## Evidence categories

| Evidence | Status and interpretation |
| --- | --- |
| Independent domain checks | **PASS: 26 tests, no skips.** Synthetic licensed JATS, an abstract-only report and an unavailable report; no provider/model calls. |
| Independent HTTP checks | **PASS: 6 tests, no skips.** The separate public saved example supplies three retained papers. Session, state and persistence checks, not live discovery. |
| Mapping and HTTP regression suite | **PASS: 136 tests, no skips; 2 dependency deprecation warnings.** Includes existing map behavior and board HTTP checks. |
| Full MVP regression suite | **PASS: 272 tests, no skips.** Reported by the coordinator. |
| Focused board frontend tests / TypeScript | **PASS: 11 component tests, no failures/skips; TypeScript exit 0.** Reported by the frontend implementation agent. |
| Full frontend suite / production build | **PASS: 54 tests, no failures/skips; production build and explicit TypeScript check exit 0.** Reported by the coordinator. |
| Actual retained-paper browser walkthrough | **PASS for the demonstrated software workflow:** three actual retained reports, nine cells, exact inspection, submission/revision, persistence, conflict recovery and local downloads. See the bounded browser record below. |
| Live PubMed / source acquisition in this checkpoint | **NOT_RUN.** Existing retained sources are reused. Historical discovery results remain historical. |
| Real embedding / generation / extraction in this checkpoint | **NOT_RUN.** Board retrieval reuses the lexical ranker; no model is required. |
| Human relevance, entailment or usefulness validation | **NOT_RUN.** Software checks and agent-entered demonstration values cannot establish scientific usefulness. |

Test counts overlap: the focused and independent board checks are included in their respective full suites. The full suites total 408 Python tests and 54 frontend tests; focused counts are not additional tests.

## Commands actually executed

From the repository root:

```sh
/private/tmp/lre-mvp-venv/bin/python -m pytest tests/mvp/test_boards_independent.py -q -rs
# 26 passed in 1.33s; no skips

/private/tmp/lre-web-venv/bin/python -m pytest tests/web_api/test_boards_independent.py -q -rs
# 6 passed, 2 warnings in 3.82s; no skips

.venv-map/bin/python -m pytest tests/mapping tests/web_api -q -rs
# 136 passed, 2 warnings in 41.36s; no skips

/private/tmp/lre-mvp-venv/bin/python -m pytest tests/mvp -q -rs
# coordinator: 272 passed in 10.99s; no skips
```

The frontend implementation agent also executed, from `apps/web`:

```sh
/Users/hunt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --import tsx --test tests/board*.test.tsx
# 11 passed, 0 failed, 0 skipped; 484.116375ms

/Users/hunt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node node_modules/typescript/bin/tsc --noEmit
# exit 0; 1.2005s
```

The coordinator executed the full frontend suite and production build from `apps/web`:

```sh
/Users/hunt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --import tsx --test tests/*.test.ts tests/*.test.tsx
# 54 passed, 0 failed, 0 skipped; 783.397ms

NEXT_TELEMETRY_DISABLED=1 /Users/hunt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node node_modules/next/dist/bin/next build
# PASS, including TypeScript checking
```

The two HTTP dependency warnings concern Starlette's deprecated `httpx` test-client integration and the deprecated `anyio.abc.BlockingPortal` alias. They were warnings, not failed or skipped assertions. No dependency migration was included in this checkpoint.

## What the independent checks establish

- A three-report by three-field definition starts with nine unassessed cells. Creating, listing and reopening it leave research snapshots and provider counters unchanged.
- Candidate retrieval stays within one report and one field, records its profile and counts, and does not create submitted values or declared inspection. Reading exact context also does not declare inspection.
- Source references are server-reconstructed, bound to the original preparation, paper, source version, block and hashes. Wrong ownership, unknown blocks, changed hashes, invalid ranges and client-supplied authoritative quotations are rejected.
- Unicode offsets use code points. Tests cover emoji, combining characters and Chinese text, candidate omissions at 1,200 code points, and complete reconstruction through inspector pages of at most 4,000 code points.
- An exact quotation remains mechanically checked while the semantic judgment stays unassessed unless explicitly changed by a human operation. Mechanical matching does not establish entailment.
- Null submissions require missing information and a reason. “Not found in inspected material” additionally requires declared inspected ranges; unavailable sources can remain “not assessed” without inventing an absence finding.
- Competing draft saves have one CAS winner. Failed draft updates and submissions preserve the acknowledged draft. Submission retry is idempotent after draft consumption; revision requires an explicit current parent. Changed definitions or sources cannot silently inherit submitted support.
- Original search bibliography is retained after a later search changes metadata. Board CSV protects formula-leading cells; canonical JSON preserves original values. Existing `mvp.audit-bundle.v1` exports retain their content and schema, excluding their normal per-export timestamp.
- Another browser session cannot read or write board resources. Mutations require the existing exact Origin and CSRF boundary. Normal projections omit full canonical blocks and quotation payloads; history, context and exports provide explicit detail.
- Deletion prevents late writes and clears board state. An interruption before sidecar cleanup leaves the workspace inaccessible; an explicit deletion retry finishes cleanup without resurrecting it.

## Review findings and corrections

| Finding | Evidence and disposition |
| --- | --- |
| Inspecting a later canonical block returned `offset=0`, making “Next source blocks” jump to the beginning | **Reproduced: one failing independent regression before correction. Fixed:** block-specific inspection reports its actual position in the nonempty canonical block sequence. The regression now passes. |
| Empty null drafts could otherwise be submitted without a missing-information explanation | **Architecture rule clarified and implemented:** initial empty cells remain unassessed; a submitted null requires a reason and missing information. Three independent negative cases pass. |
| Idempotent candidate/submission replay must still check retained source integrity | **Hardened during review:** cached results revalidate original dependencies before returning. Two independent tamper-after-cache cases pass. |
| Older comparison-page reads could overwrite a newer selected board definition | **Fixed and regression-tested:** generation guards reject older success/error responses and prevent a view from rendering under a different selected revision. |
| Initial draft-read failure could make retry treat an untouched local empty draft as competing edits | **Fixed and regression-tested:** retry restores the saved server draft when there have been no local edits and the initial read never succeeded. Dirty competing edits retain CAS conflicts. |
| Export-history checkbox implied that unchecked audit exports omit all superseded cells | **Semantics clarified:** audit JSON always includes all cell revisions and candidate runs for the selected definition. The option includes earlier board definitions as well; the UI label and explanatory text now say this. CSV contains the selected definition's current table. |
| A historical definition retained its unsent draft in storage but the editor displayed only its submitted head | **Fixed and regression-tested:** a separate read-only “Retained historical draft · not submitted” view exposes the retained data and CAS binding. It does not change submitted states, write the draft or apply it to another definition. |

Early independent test failures also exposed test assumptions: inspector context starts at a bounded absolute offset; compact heads differ from full history records; legacy exports contain a fresh timestamp; and a synthetic full-text fixture needs valid retained XML and permission metadata. The tests were corrected, including explicit assertions that the fixture really contains full-text, abstract-only and unavailable sources. These test corrections are not reported as product fixes.

## Retained-paper preparation for the browser check

The evaluation inspected the existing private research snapshot read-only and ran the existing lexical ranker locally. The chosen three retained reports include two full texts (54 and 98 canonical blocks) and one abstract-only source (one block). For the abstract-only source, the population and limitations questions returned zero lexical candidates while the study-design question returned one. Zero matches remain a retrieval result, not an absence finding.

Exact source hashes, candidate anchors and titles are kept in the ignored local receipt `.mvp-web-state/ui-checks/manual-board-2026-10-21/retained-paper-plan.json` with file mode `0600`. No private quotations or workspace credentials are included in this document. This preparation made no provider/model calls and did not alter saved research state.

## Actual browser workflow

The coordinator operated the local production interface on the three retained reports described above. Browser actions and downloaded artifacts are recorded privately in `.mvp-web-state/ui-checks/manual-board-2026-10-21/browser-receipt.json`, alongside local CSV/JSON exports and screenshots. The evaluator read the receipt and its counts; this document does not reproduce private quotations or workspace identifiers.

| Browser action | Observed result |
| --- | --- |
| Create a board with three prepared reports and three editable fields | Nine independent cells, using the existing retained preparation; no discovery or source-acquisition rerun. |
| Retrieve candidates for every report/field pair | Nine persisted candidate runs; candidates remained separate from inspected ranges and submitted support states. |
| Inspect exact canonical source text, select ranges, enter manual values and explicitly submit | Nine current table rows. All reference-integrity states were checked; every semantic assessment remained **unassessed**. Values were labeled as a software walkthrough. |
| Inspect the abstract-only source and record an explicit missing-information case | One null cell with an explanation and declared inspected scope. It was not presented as absence from the full paper or literature. |
| Revise submitted cells and reopen an earlier citation | Eleven immutable submitted revisions across nine cells; the historical citation opened its original retained context. |
| Save a draft, restart the local server and reload/reopen | The acknowledged draft survived and reopened in the same browser session. |
| Edit from two browser tabs | A stale save returned 409, retained the conflicting edits and blocked normal navigation. Explicit rebasing and submission completed recovery. |
| Download board CSV and audit JSON through the browser | CSV contained nine table rows. JSON contained nine table rows, eleven immutable cell revisions and nine candidate runs. Private local exports were hash-recorded in the receipt. |
| Inspect the narrow layout at 390 px | Body width was 390 px. The table's 342 px focusable region scrolled its 620 px content instead of widening the page. |
| Final smoke after the final production build/restart | The same nine-cell board refreshed successfully, the submitted null was clearly labeled “Not found in inspected material”, and browser console errors were empty. The temporary viewport was reset. |

One computer-use action encountered a detached element after cell navigation. The coordinator re-observed the page and repeated the click successfully. This was an automation-target transient, not an application failure. A separate null-cell matrix ambiguity was corrected so submitted null/missing information is distinguishable from an untouched cell.

Definition-revision navigation and recovery of historical unsent drafts were covered by software tests, **not** an actual browser walkthrough in this checkpoint. The browser workflow does not validate research relevance, review quality, human usefulness or scientific entailment.

## Changed files and preservation

The scoped checkpoint files are:

| Area | Files |
| --- | --- |
| Domain contracts/service/storage | `src/mvp/board_contracts.py`, `src/mvp/evidence_board.py`, `src/mvp/adapters/board_storage.py` |
| Existing API integration | `src/web_api/board_routes.py`, `src/web_api/app.py`, `src/web_api/contracts.py` |
| Browser implementation | `apps/web/components/compare.tsx`, `apps/web/components/workspace-app.tsx`, `apps/web/lib/board-drafts.tsx`, `apps/web/lib/drafts.tsx`, `apps/web/lib/bridge.ts`, `apps/web/app/globals.css` |
| Generated contracts | `apps/web/lib/openapi.json`, `apps/web/lib/generated-api.ts` |
| New frontend checks | `apps/web/tests/board-boundaries.test.ts`, `apps/web/tests/board-drafts.test.tsx`, `apps/web/tests/board-workflow.test.tsx` |
| Existing frontend capability fixtures | `apps/web/tests/discover-selection.test.tsx`, `apps/web/tests/map-navigation.test.tsx`, `apps/web/tests/map-selection-integration.test.tsx`, `apps/web/tests/offline-example.test.tsx`, `apps/web/tests/query-suggestions.test.tsx` |
| Domain/API checks | `tests/mvp/test_boards.py`, `tests/mvp/test_boards_independent.py`, `tests/web_api/test_boards_independent.py` |
| Documentation | `docs/manual_comparison_board.md`, `docs/manual_board_evaluation.md`, `docs/mvp_v0_3.md`, `docs/mvp_v0_3_board_plan.md` |

The table lists exactly 29 scoped files. The five existing frontend test fixtures changed only to accommodate the additive board capability. Of the coordinator's 681-file preservation inventory, 676 files remained unchanged and those five fixture changes were intentional; the intentionally updated plan/status documents were outside that initial inventory. The coordinator separately verified unchanged payload hashes for all twenty existing research snapshots. Private board state is additive in `evidence-boards.sqlite3`; historical research payloads were not migrated or rewritten, and board operations do not request map refits. Existing OpenAPI paths remain unchanged; among existing schemas, only `Capabilities.boards` was added. Pre-existing `.gitignore` and README edits, research experiments and other unrelated local files remain outside this checkpoint's changed-file scope.

The branch remains `codex/mvp-v0-3` based on the requested commit. No merge, push, deployment or private-data publication is part of this checkpoint. Startup instructions are in [the manual-board guide](manual_comparison_board.md#start-locally).

## Remaining limits

- The board records single-human, self-declared judgments, not independent verification or study quality ratings.
- Lexical matches can be empty or irrelevant. Reviewers must inspect canonical text and explicitly record their scope and judgment.
- Durability applies to acknowledged server drafts and submissions. Unsaved or failed edits are retained in the mounted browser session; they are not a guarantee against closing or clearing the browser before saving.
- The local browser session remains the authorization mechanism. Clearing its cookies does not provide UUID-only account recovery.
- Definition revisions deliberately start new unassessed cells. There is no automatic carry-forward or extraction proposal in this checkpoint.
- Browser evidence covers the specified retained-paper slice and conflict recovery. Definition-revision and historical unsent-draft behavior have software evidence only; cross-browser accounts, multi-reviewer verification and scientific usefulness remain outside this checkpoint.
