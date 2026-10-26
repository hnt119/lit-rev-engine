# Question-to-evidence checkpoint — observed validation

## Identity and publication boundary

Baseline: current reviewed main `265b291aaf0a2a60ac9aa89862dc531a78207874`, containing published source beta.4 `d52e5e35c80ef435abaec0c0a6f4ed236cba9356`. Feature branch: `codex/question-evidence-workbench`. The macOS checks below were performed against uncommitted development inputs, not a replacement beta.4 download or a new release. The owner subsequently authorized committing/pushing this feature branch and running Core-only Windows CI. See [the Windows execution record](question_evidence_windows_validation.md) for that separate status. No main merge, release publication, deployment, private-data upload or model/provider spending is authorized by that CI approval.

The 254 application inputs used for the production build/browser checks had aggregate SHA-256 `aea51de31c1507e526d40713f1e6f943c6262e5bf6f4b0060191475df9f0d583` and remained identical after browser/restart checks. This is a working-input fingerprint, not a Git commit or a release-asset checksum. All pre-existing OpenAPI schema definitions and existing paths remain structurally equal to the baseline; new contracts/routes are additive. Original compiler, rankers, pinned profiles, scientific board/cell DTOs and source parser files have no changes.

## Fresh software results

Environment: macOS **26.6.2 (25G83), arm64**; Python **3.12.7**, Node **24.19.0**, existing locked frontend dependencies. Production Chrome **155.0.8059.85**, sandbox enabled. Test/runtime state was newly created outside the app. Original research databases, cookies, user workspaces and Track B were not used. This is source/development validation, not a fresh downloaded-app/native-installer test.

| Check | Actual result | Scope |
| --- | --- | --- |
| MVP backend suite | **814 passed, 13 skipped**, 27.29 s | Existing engine plus additive typed-view service; offline fixtures |
| Complete HTTP suite | **437 passed**, two existing dependency deprecation warnings, 291.25 s | Ownership, source/cell/draft/CAS, configuration, imports, proposal mocks and historical compatibility |
| Complete frontend suite after focus fix | **211 passed, zero failures/skips**, 3.35 s | Search, comparison, drafts, bridge, facets, delayed return-focus and existing workflows |
| TypeScript and production Next build | **PASS** | Same application and thin FastAPI bridge; no dependency upgrades |
| Production browser create phase | **9 checkpoints passed**, 201 local API requests, 9.236 s driver time | Three retained public full-text reports, five fields; synthetic unreviewed values only |
| Actual process restart/reopen | **PASS** | Same browser session, saved view, unsent cell draft and byte-identical full-board CSV/JSON |
| Browser external requests / page errors | **0 / 0** | Both browser phases; no live or model operation |
| Narrow viewport / keyboard | **PASS** | 390 px viewport without page-width overflow; horizontal table scrolling; original-cell focus and filtered-report recovery |
| Existing Windows signal adapter tests | **2 passed on macOS** | Contract checks only; not Windows execution |
| Prepared Windows offline command | **79 passed on macOS**, two existing warnings, 8.20 s | Same native-fixture test selection; actual Windows execution NOT_RUN |
| Source/privacy/link/diff audit | **PASS** | No new credentials, personal paths, databases, runtime/cache/weight artifacts; document links checked |

The 13 MVP skips are legacy optional Streamlit checks: two acceptance UI smokes, four draft regressions, three navigation checks, three presentation checks and the Streamlit preparation-job module. The isolated Core test environment lacks their focused UI dependencies / `streamlit.testing.v1`. They were not silently counted as passes. The existing Starlette/httpx/AnyIO and React test-renderer deprecation notices remain; no dependency upgrade was made.

## What the production browser actually did

1. Created an offline workspace, retained an exact CRLF specialist query, explicitly approved it, saved later extraction questions and downloaded a readable strategy. Live execution/diagnostics stayed disabled in this mode. The saved example is independent of that query; it is not presented as a PubMed query result.
2. Prepared three already-permitted public reports and a five-field comparison, selected Overview and verified that navigation/view selection ran no retrieval, preparation, generation or provider operation.
3. Found a Core lexical excerpt, inspected its canonical source, attached it explicitly, entered a clearly synthetic unassessed note and saved through the existing editor. No scientific support judgment or independent verification was fabricated.
4. Explicitly bound specimen normalization to an existing field, entered two synthetic values as unreviewed, preserved a profile draft through source-cell navigation, opted into unreviewed facets, filtered/grouped and saved a named view. Its filtered JSON contained only the one matching report.
5. Retained an unsent cell edit across passage search, exact source inspection, return, browser Back and refresh. Navigation alone did not search or attach evidence.
6. Saved an explicit cell revision. The earlier typed normalization correctly became outdated and stopped matching its facet. The UI retained the original target, displayed an explicit recovery action and restored keyboard focus after the matching rows rendered.
7. Kept a new unsent note, exported, restarted both actual production processes, reopened with the same authorized browser session and verified the view/draft and unchanged CSV/JSON export hashes. Shutdown released only owned listeners.

Abstract-only, unavailable-source, insufficient-information, wrong-paper/proposal, stale-source, concurrent-tab, malformed-input, quoted-text and historical cases were checked with disclosed synthetic API/component fixtures. They were **not** all repeated in the public-full-text browser case. A software enum fixture marked `human_supported` is not a participant assessment.

## Failures found and corrected

Review caught and fixed missing Next bridge entries/mutation query allowances, formula-unsafe/overbroad filtered exports, missing visible scientific cells in current-view exports, incomplete design-note draft rejection, history-navigation draft-loss/late responses, saved-view reload baselines, profile refresh baselines/affirmation/idempotency scope and save-acknowledgment navigation barriers.

The actual browser found one keyboard return race: revealing a filtered-out cell could focus before its new rows committed. It now queues the exact target/config until a matching view renders, consumes focus once, and does not steal focus on later filters. A delayed-response regression and the actual browser passed afterward.

Initial harness runs also exposed exact-label selector ambiguity in native controls, an outdated expectation that a revised classification should still match, and old component fixtures that did not implement the new read-only view projection. Those harness expectations were corrected; scientific no-write, ownership and source-binding checks were retained. One broad pytest attempt used an incompatible import mode and stopped with collection errors; the repository's existing separate/default suite invocations above passed. No production workaround weakened a boundary to obtain a pass.

## Commands and reproducibility

The commands below use the already installed isolated Python/Node versions named above; they do not claim fresh package installation. Run the MVP and API suites separately because existing cross-test fixture imports use their default import convention.

```sh
python -m pytest -q -rs -p no:cacheprovider tests/mvp
python -m pytest -q -p no:cacheprovider tests/web_api
python scripts/export_web_openapi.py
cd apps/web
node node_modules/openapi-typescript/bin/cli.js lib/openapi.json -o lib/generated-api.ts
node node_modules/typescript/bin/tsc --noEmit --incremental false
node --import tsx --test tests/*.test.ts tests/*.test.tsx
NEXT_TELEMETRY_DISABLED=1 node node_modules/next/dist/bin/next build
```

`tests/workbench/browser_workbench.cjs` takes a Playwright module directory, explicit loopback origin, fresh private QA directory and `create` / `verify`. Start this source's production app with a new external data directory and live/model features disabled; run create, stop both owned services, restart with the same data, then run verify using the retained private QA session. Never upload that directory: it contains browser authorization, exports and screenshots. On macOS the test used system Chrome with its sandbox enabled. The existing Windows source runner now invokes the same driver after its original workflow and after restart/replacement; it has **not been dispatched for this increment**.

## Resource case and sample exports

See [the safe machine-readable aggregate](question_evidence_validation_software.json) for exact API-input and synthetic sample-export hashes. It is a separate isolated TestClient case, not a browser or human benchmark: fifteen synthetic cells over full-text/abstract/unavailable fixtures; thirty-report scale with 150 unassessed cells; ten warm projection calls per size. Measured medians were **11.188 ms / three reports** and **24.725 ms / thirty reports**. Peak RSS was **119,619,584 bytes** for that Python process including imports, tests and both cases, not whole-app/browser/model memory. The shared host was not an exclusive performance environment. No comparison, speedup, scientific-quality or human-time claim follows.

Sample exports are local synthetic software examples; none is a human gold table or a new public research dataset. The resource aggregate labels its exact uncommitted input binding and omits private QA paths, cookies, participant data and article quotations.

## Remaining gates and limits

- **Windows execution of the changed checkpoint: NOT_RUN.** Existing beta.4 Windows evidence is historical and cannot qualify these changes. The affected API step and portable production-browser driver are prepared. The owner has now authorized a feature-branch commit/push and Core-only CI (`run_models=false`); the [separate execution record](question_evidence_windows_validation.md) distinguishes actual results from this earlier macOS-only record. Physical Windows 11 and native downloaded-app validation are also NOT_RUN.
- **Live PubMed, real optional models and generation: NOT_RUN.** Compiler/diagnostic/provider behavior is fixture/mocked coverage. No new model-quality gain or superiority over BM25 is asserted.
- **Participant, usual-workflow, strong-LLM and competitor evaluation: NOT_RUN.** The [blank evaluation kit](question_evidence_evaluation/README.md) has no populated observations or invented reference findings. Source access, criteria, held-out seeds and comparator conditions must be fixed before an actual session.
- Authoritative controlled-vocabulary verification is unavailable; external execution records remain researcher-reported. The new classification is explicit report-level normalization, not eligibility or same-cohort inference. Filtering can reveal gaps; it does not fill them.
- PDF attachment remains a separately documented web-workflow gap. No publisher login, copied cookies, paywall bypass or new attachment engine was added.
- No release ZIP/native executable was rebuilt or distributed. Published artifacts, main, the portfolio, deferred hosted implementation, native packaging and Track B remain outside this change. Existing cookie/access-recovery limits remain.

## Packaging and CI follow-up

After the owner authorized feature-branch push and Core-only Windows CI, review found that the extracted manual's new task-guide link had no packaged target. The packaging allowlist now includes exactly 24 approved workbench documents and blank-template files, with one deterministic guide-to-manual alias rewrite. Nine CSV templates require their exact header and no observation rows. Both the builder and independent archive auditor check local Markdown targets without fetching external links. Targeted packaging tests: **39 passed, zero skipped**; actual current documentation closure also passed. The staged audit also removed one extra blank line at EOF from the extracted raw-query editor; it changes no program behavior. Frontend/type checks were rerun after that formatting correction. These follow-ups do not change published beta.4 assets or runtime features. Windows execution is recorded separately.

## Changed files

Only these source, configuration, documentation and test files form the reviewed feature change. Runtime and private data are excluded.

- `.github/workflows/windows-source-validation.yml`
- `README.md`
- `apps/web/app/globals.css`
- `apps/web/components/compare.tsx`
- `apps/web/components/evidence-views.tsx`
- `apps/web/components/raw-strategy-editor.tsx`
- `apps/web/components/search-concept-cards.tsx`
- `apps/web/components/search-design-notes.tsx`
- `apps/web/components/search-diagnostic-summary.tsx`
- `apps/web/components/search-planner.tsx`
- `apps/web/lib/bridge.ts`
- `apps/web/lib/evidence-views.ts`
- `apps/web/lib/generated-api.ts`
- `apps/web/lib/openapi.json`
- `apps/web/lib/search-design.ts`
- `apps/web/tests/board-workflow.test.tsx`
- `apps/web/tests/comparison-passage.test.tsx`
- `apps/web/tests/evidence-focus.test.tsx`
- `apps/web/tests/evidence-views.test.tsx`
- `apps/web/tests/search-design-usability.test.tsx`
- `apps/web/tests/workbench-bridge.test.ts`
- `docs/question_evidence_access_audit.md`
- `docs/question_evidence_evaluation/README.md`
- `docs/question_evidence_evaluation/acceptance.md`
- `docs/question_evidence_evaluation/analysis.md`
- `docs/question_evidence_evaluation/comparators.md`
- `docs/question_evidence_evaluation/observer.md`
- `docs/question_evidence_evaluation/participant.md`
- `docs/question_evidence_evaluation/protocol.md`
- `docs/question_evidence_evaluation/seed_lock.md`
- `docs/question_evidence_evaluation/tasks.md`
- `docs/question_evidence_evaluation/templates/assignments.csv`
- `docs/question_evidence_evaluation/templates/conditions.csv`
- `docs/question_evidence_evaluation/templates/documents.csv`
- `docs/question_evidence_evaluation/templates/field_checks.csv`
- `docs/question_evidence_evaluation/templates/issues.csv`
- `docs/question_evidence_evaluation/templates/observer_events.csv`
- `docs/question_evidence_evaluation/templates/participant_feedback.csv`
- `docs/question_evidence_evaluation/templates/seeds.csv`
- `docs/question_evidence_evaluation/templates/timings.csv`
- `docs/question_evidence_user_guide.md`
- `docs/question_evidence_validation.md`
- `docs/question_evidence_validation_software.json`
- `docs/question_evidence_windows_validation.md`
- `docs/question_evidence_workbench.md`
- `docs/user_manual.md`
- `scripts/build_local_preview.py`
- `src/mvp/adapters/board_storage.py`
- `src/mvp/adapters/search_plan_storage.py`
- `src/mvp/evidence_view_contracts.py`
- `src/mvp/evidence_views.py`
- `src/mvp/search_plan_metadata.py`
- `src/web_api/app.py`
- `src/web_api/evidence_view_routes.py`
- `src/web_api/search_plan_routes.py`
- `src/web_api/search_strategy_routes.py`
- `tests/local_distribution/audit_source_archive.py`
- `tests/local_distribution/test_release_packager.py`
- `tests/local_preview/test_workbench_package_docs.py`
- `tests/mvp/test_evidence_views.py`
- `tests/web_api/test_question_evidence_checkpoint.py`
- `tests/web_api/test_search_design_metadata.py`
- `tests/windows/run_source_acceptance.py`
- `tests/workbench/browser_workbench.cjs`
