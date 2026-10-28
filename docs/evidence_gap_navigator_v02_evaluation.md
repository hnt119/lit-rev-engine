# Evidence Gap Navigator v0.2 — software evaluation

Goal and scope: improve persistent navigation, share one reviewed Core concept builder, and connect an insufficient-evidence assessment to attributed research notes or an explicit expanded comparison. This is a development increment stacked on PR #22; neither PR is merged by this task.

Base: `749aef22b66bf88ace951548e4d704b8d8977485` (`codex/evidence-gap-navigator-v01`). Implementation and recorded-browser source: `1161b0eae91ade974ed1f3c58d782df38745ed41` (`codex/evidence-gap-navigator-v02`). The following report/link commit changes documentation only. The original v0.1 checkout and its preview remain separate.

## Review increments and behavior

- `bc79d61`: bounded sticky navigation, available subsection links, focus/scroll preservation and compact narrow layout.
- `14aec99`, `de46899`: shared deterministic Core suggestions, explicit concept/term review and Boolean strategy construction, including exact preservation of compact Boolean, wildcard, quoted and fielded specialist input.
- `1572e19`: explicit shortlist-to-collection handoff, immutable investigation origins, verified passage receipts, versioned research evaluation notes and audit v2.
- `1161b0e`: assessment entry points, existing preparation/retrieval/board integration, source-bound comparison provenance, durable typed draft and real-browser test fixture.
- Separate test commits cover draft authorization, mounted workflow behavior and distinct logical collection/snapshot identities. Documentation is kept in the existing [feature guide](evidence_gap_navigator.md), [query guide](query_suggestions.md) and [manual](user_manual.md).

The integration owner coordinated disjoint navigation, query and backend changes in separate temporary clones. Application changes use existing services and contracts; no new model framework, database or research engine was introduced. New contracts are `CoreConceptSuggestion`, `InvestigationMemberOrigin`, handoff/inspection/research-note models, and the incomplete-input `InvestigationResearchDraft`. The generated HTTP client is regenerated from FastAPI.

## Checks actually run

Environment: macOS arm64, Python 3.12.7, Node 24.19.0, locked web dependencies, production Next.js build and sandboxed Chrome. All research data is synthetic or the existing rights-checked public offline fixture corpus. External provider transport is denied in browser QA; no private workspace is used.

| Check | Result |
| --- | --- |
| `python -m pytest -q -rs tests/mvp` on implementation source | **822 passed, 13 skipped** in 26.55 s. Skips require optional Streamlit testing dependencies. One cache-write warning in the managed checkout; test execution passed. |
| `python -m pytest -vv -o faulthandler_timeout=40 tests/web_api` | **487 passed** in 317.01 s, including the populated 30 × 6 capacity case. Two existing dependency deprecation warnings. |
| `pnpm --dir apps/web test` | **223 passed**, no failures/skips. |
| `pnpm --dir apps/web typecheck` and production `build` | Passed; committed managed-worktree build also passed. |
| OpenAPI and TypeScript client re-export byte comparisons | Passed. Generated TypeScript also compiled with the application. |
| Production browser at 1440, 390 and 320 px | Passed, zero page errors. Real application components and offline source providers. |
| Dedicated headed browser after service restart | Passed: original board, committed selection and two evaluation revisions reopened with the original session protections. |
| Legacy collection compatibility | Old origin variants and both metadata formats retained canonical serialized bytes/hashes; old compressed collections and prepared member snapshots remained readable. |
| Whitespace and documentation target checks | Passed. |

The final browser test covers contextual investigation from a submitted partial cell; shared Core suggestions; explicit AND/OR review; query-edit approval invalidation; simulated search; manual shortlist/dismiss; reviewed immutable collection; explicit preparation and selection of prepared sources; verified Paper B passage; attributed note and revision; immediate-edit navigation/refresh retention; responsive subsection navigation; expanded comparison with all cells unassessed; original historical-source inspection; and readable/JSON audit export. Subsection navigation makes no HTTP request in the navigation acceptance checks. Retrieval/preparation/search require explicit actions.

API and component checks also cover saved-example restrictions, live-workspace configuration, ownership/CSRF, stale source and decision bindings, source tampering and Unicode ranges, unavailable/failed preparation, duplicate/conflicting identifiers, capacity/byte quotas, idempotent request replay, two-tab conflicts, deletion races, and inspection/note provenance. A shortlist or unprepared citation cannot become a verified note attachment.

### Corrections and unsuccessful attempts retained

The initial combined `tests/mvp tests/web_api` invocation failed collection because existing test filenames collide; the suites were run separately. An initial API run was interrupted while the existing large capacity test was slow (486 cases had completed); the diagnostic rerun completed all 487. The 40-second diagnostic dump showed active decoding/submission in that capacity test, not a v0.2 storage deadlock. Counts above are separate runs and are not summed.

Review and integration testing corrected: a nested lifecycle lock in the new draft route; coercible checkbox values; incomplete navigation flushing; hidden selected-but-dismissed candidates; reselecting the active handoff resetting retrieval; reopened job publication replacing an explicit historical preparation; original-report passages incorrectly offering a related-paper note action; logical collection IDs used where snapshot IDs were required; and specialist query syntax being reduced to keywords. Targeted regressions now cover these boundaries.

Browser harness corrections included a required fixture request ID, accessible link/action selectors, required acknowledgments after switching to a specialist strategy, waiting for restored draft state, and waiting for owned services to stop before restarting. These unsuccessful attempts are not treated as successful acceptance runs.

## Local preview and recording

The task's local artifact bundle contains **Open-preview.command**, **Stop-preview.command**, **README.txt**, a 63-second captioned silent MP4, readable and JSON audit exports, viewport screenshots, and preservation/reopen checks. The actual app runs on loopback ports 51871/51872 using a separate private data directory and dedicated browser profile. The video is an actual browser screen capture, with captions outside the application pixels; narrow views are letterboxed.

The provider is visibly labeled **SIMULATED SEARCH** and returns fixed public fixture papers independent of the supplied query. Original and follow-up source text comes from the existing checked fixture provider. This establishes software behavior, not PubMed translation, relevance or scientific usefulness.

Portable reproduction uses the checked-in `tests/investigations/offline_research_server.py` with a newly created temporary data directory and free API/web ports, the production web build with matching `MVP_API_ORIGIN`/`MVP_WEB_ORIGIN`, then `tests/investigations/research_browser_flow.cjs PLAYWRIGHT_RUNTIME WEB_ORIGIN OUTPUT_DIRECTORY`. The Playwright runtime argument is a directory containing `node_modules/playwright`. Set `LRE_RECORD_DEMO=1` only when screenshot recording is desired. The checked-in browser test uses fresh browser context/storage by default; no existing profile or research directory is required.

## Limits and NOT_RUN

- Core uses bounded lexical rules and a small explicit wording table. Unknown roles require review. It is not a biomedical terminology validator, general natural-language parser or MeSH validator. Parentheses/quotes/wildcards can conservatively preserve the entire input as a specialist strategy. Recall/precision claims are not made.
- A research evaluation revision attaches one exact passage and researcher interpretation. It is separate from the original paper's cell; there is no automatic scientific synthesis, eligibility decision, conflict judgment or gap score.
- Explicit source preparation changes the workspace's current source revision. The original comparison therefore becomes historical/read-only when its dependencies differ; its definition, evidence, drafts, judgments and exact references stay retained. Expanded boards start unassessed, including selected previous reports.
- Existing limits remain 30 reports and 6 fields. Metadata conflicts need explicit resolution. Missing sources stay unavailable. Commit, preparation, inspection, note saving and board creation remain separate actions.
- Completed expanded boards are reopened through the ordinary comparison list; source-linked provenance provides an original-board link. There is no automatic migration of prior reviewed cells.
- **NOT_RUN:** real PubMed search/diagnostics, paid or local models, human usefulness study, scientific validity or retrieval quality, native Mac/Windows installer qualification, physical mobile-device testing and optional Streamlit UI checks.

Git/research/publication status: scoped v0.2 review branch; PR #22 remains open and unmerged. No main merge, release tag/installer publication, personal-website edit, Track B integration, paused mobile-prototype change or private research access. The interactive preview is intentionally left running with owned-process stop instructions.

## Exact affected files

Paths below are relative to the repository; generated contracts are included deliberately.

```text
apps/web/app/globals.css
apps/web/components/compare.tsx
apps/web/components/comparison-lineage.tsx
apps/web/components/core-concept-builder.tsx
apps/web/components/discover.tsx
apps/web/components/evidence.tsx
apps/web/components/history.tsx
apps/web/components/investigation-navigator.tsx
apps/web/components/investigation-research.tsx
apps/web/components/research-settings.tsx
apps/web/components/search-planner.tsx
apps/web/components/workspace-app.tsx
apps/web/components/workspace-navigation.tsx
apps/web/lib/bridge.ts
apps/web/lib/core-concepts.ts
apps/web/lib/generated-api.ts
apps/web/lib/investigation-research.ts
apps/web/lib/openapi.json
apps/web/lib/workspace-sections.ts
apps/web/tests/core-concepts.test.tsx
apps/web/tests/investigation-research.test.tsx
apps/web/tests/investigations.test.tsx
apps/web/tests/workspace-navigation.test.tsx
docs/evidence_gap_navigator.md
docs/evidence_gap_navigator_v02_evaluation.md
docs/query_suggestions.md
docs/user_manual.md
src/mvp/adapters/investigation_storage.py
src/mvp/collection_contracts.py
src/mvp/core_concept_suggestions.py
src/mvp/investigation_draft_contracts.py
src/mvp/investigation_research.py
src/mvp/investigation_research_contracts.py
src/mvp/investigations.py
src/web_api/app.py
src/web_api/investigation_routes.py
src/web_api/search_plan_routes.py
tests/investigations/offline_research_server.py
tests/investigations/research_browser_flow.cjs
tests/mvp/test_core_concept_suggestions.py
tests/web_api/test_core_concepts_http.py
tests/web_api/test_investigation_research.py
tests/web_api/test_investigation_research_drafts.py
```
