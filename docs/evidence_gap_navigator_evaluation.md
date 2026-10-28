# Evidence Gap Navigator v0.1 — software evaluation

**28 October 2026.** Researcher-controlled follow-up investigation from one unresolved comparison cell. This is development-source validation, not a published-release, scientific-quality or human-usefulness claim. [User guide](evidence_gap_navigator.md).

## Scope and provenance

```text
Goal and scope: create, edit, approve, execute, manually shortlist, reopen, export and return.
Base: c076065f28fbc7363ba43a5607304d2987d79faa (origin/main at task start).
Implementation: 215e923f890937838aca05ff52dfadad919d2783.
Owner: one integration branch, codex/evidence-gap-navigator-v01; separate backend/frontend clones.
Paths: src/mvp, src/web_api, apps/web components/contracts/tests, focused tests and guide.
Publication boundary: implementation PR only; no merge, release/tag/asset or website change.
Research boundary: temporary public/synthetic fixtures; original private research untouched.
```

The workbench branch `ec7897f82005eba924475848164782848d8a1708` was inspected. Main already contains its deterministic search compiler, search-plan/approval contracts and diagnostic/discovery services. Those existing contracts are reused. The entire workbench branch, typed-attribute platform, Track B and mobile prototype were not merged. Needs review is a workflow filter on the existing comparison table.

New versioned investigation contracts retain the original board definition, exact paper/field, submitted cell, saved draft, separately labeled local editor snapshot, source manifest, researcher reason and seed-plan provenance. Follow-up previews and append-only decisions use bounded auxiliary tables in the existing SQLite database. They do not change workspace searches/question, board definitions, cells, preparations or sources. Existing session, Origin/CSRF, lifecycle, ownership and provider throttling boundaries remain in force.

## Checks actually run

Environment: macOS 26.6.2 (25G83), arm64; Python 3.12.7, FastAPI 0.153.0, Pydantic 2.13.4, pytest 9.1.0; Node 24.19.0; existing pinned Next 16.4.2/React 19.3.1 dependencies. Production Chrome 156.0.8078.49 used a fresh disposable profile with the Chromium sandbox enabled. All application traffic was restricted to loopback; providers were mocked and external Python transport was denied.

| Check | Result |
| --- | --- |
| `python -m pytest -q -rs -p no:cacheprovider tests/mvp` | **802 passed, 13 skipped**, 27.60 s. Skips require optional Streamlit testing dependencies. |
| `python -m pytest -q -p no:cacheprovider tests/web_api -k 'not populated_thirty_by_six'` | **442 passed, 1 deselected**, 136.91 s. Existing large capacity case run separately below. |
| Selection limits + usability capacity/drafts/passages API files | **49 passed**, 176.30 s; includes the populated 30-paper × 6-field case. Overlaps the prior row; do not sum counts. |
| `python -m pytest -q -p no:cacheprovider tests/web_api/test_investigations.py tests/web_api/test_investigations_adversarial.py` | **31 passed**, 17.59 s on the committed implementation. |
| `pnpm --dir apps/web test` | **209 passed**, no skips. Includes mounted query invalidation, conflict retention, failed-provider reporting and comparison preservation tests. |
| `pnpm --dir apps/web typecheck` and `pnpm --dir apps/web build` | **PASS** on the committed implementation. |
| OpenAPI regeneration and byte comparison | **PASS**; eight added route paths and ten schemas; existing paths/schemas semantically unchanged. TypeScript client generated with the pinned generator. |
| Committed `tests/investigations/browser_flow.cjs` against production build | **PASS**; 1440- and 390-pixel widths, no document overflow, no browser page errors. |

The broad API and frontend suites preceded the final route-registration ordering cleanup, which reduced generated-file churn without changing existing schema semantics. The 31 investigation tests, OpenAPI parity, typecheck, production build, core suite and committed browser test were verified afterward at the implementation SHA above. API runs emitted two existing Starlette/AnyIO deprecation warnings; component tests emitted the existing React test-renderer deprecation notice.

The browser journey exercised reason capture, exact query approval, explicit diagnostic and execution, Shortlist/Dismiss/Leave unassessed, JSON download, changed-query approval invalidation, actual two-tab editor conflict and explicit recovery, keyboard activation/focus restoration, Needs review, refresh/reopen, Back/Forward and return to a historical board revision. It compared the original workspace, board audit and saved draft before/after the follow-up. Exactly one diagnostic and one follow-up execution occurred; navigation/decisions/exports added no source preparation, search capture or cell submission.

API coverage includes saved-example restrictions, configured-disabled live PubMed, exact approval/hash/revision binding, failed/pending request replay, duplicate IDs, cross-session/workspace isolation, stale origins and decisions, source-reference validation, storage reservation before I/O, deletion and in-flight revision fencing, concurrent audit snapshots and historical-reference readability.

## Corrections and limits

Independent review found and verified repairs for unvalidated local-draft anchors, unsafe Markdown audit rendering, concurrent export/query omissions, sticky editor-draft conflict recovery, historical return reopening the panel and citation-fetch errors looking like zero results. Early harness attempts also corrected a missing FastAPI runtime, a synthetic DOI, an asynchronous saved-query wait and a noncanonical temporary path. The initial full API run was interrupted during the slow existing capacity test after 404 passes; it is not reported as a full-suite pass. The completed runs above cover that case separately.

**NOT_RUN:** real PubMed execution, real model calls, researcher usefulness, scientific relevance/eligibility/support evaluation, native Mac/Windows installation and release qualification. No automated scientific judgment, conflict judgment, gap score, paper addition, source replacement or cell submission is implemented. A shortlist is private candidate organization, not evidence about the original paper. No background-provider work is promised.

The application retains its existing browser-cookie access/recovery limits. Investigation exports are private audit records, not a complete backup or transferable authorization. Owned test servers and browser profiles were stopped after validation; raw QA data and screenshots are not included in the PR.

## Reproduce the browser check

Use a separate private temporary directory, free loopback ports, the repository's pinned Python/web dependencies and a separately installed Playwright test runtime. Do not point this test at a real workspace. In separate terminals:

```sh
python tests/investigations/offline_server.py "$PWD" "$QA_DIR" 18765 13000
MVP_DEPLOYMENT_MODE=local MVP_API_ORIGIN=http://127.0.0.1:18765 MVP_WEB_ORIGIN=http://127.0.0.1:13000 pnpm --dir apps/web exec next start --hostname 127.0.0.1 --port 13000
LRE_BROWSER_CHANNEL=chrome node tests/investigations/browser_flow.cjs "$PLAYWRIGHT_TOOLS" http://127.0.0.1:13000 "$QA_DIR"
```

`PLAYWRIGHT_TOOLS` contains `node_modules/playwright`; omit `LRE_BROWSER_CHANNEL` to use its separately installed Chromium. `QA_DIR` must already exist and be private. Build the web app first. Stop only these owned processes and remove their disposable QA directory afterward. The test server denies external transport and returns synthetic candidates; it cannot establish live-provider success.
