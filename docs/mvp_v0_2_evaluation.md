# MVP v0.2 evaluation — checkpoints A and B

Evaluated on **20–21 October 2026**, in the working tree of `codex/mvp-v0-2`, based on
`8df5993c86893d47620a101a2319c564cff2d494`. The v0.2 changes were uncommitted when
these checks ran. These results describe local working files, not a published
commit, a hosted deployment, or a scientific validation.

The subsequent publication request authorizes committing and pushing v0.2 to
`codex/mvp-v0-2` only. This report retains the implementation-time results;
publication does not add live PubMed or scientific validation, change `main`, or
deploy the app. The [change inventory](mvp_v0_2_changed_files.md) records the
scoped publication contents and exclusions.

**Checkpoint A is ACCEPTED for the offline local workflow:** service/API checks
pass and the real browser workflow, reopening and draft-conflict fix were
rechecked. **Checkpoint B is ACCEPTED for the implemented offline local
workflow**, including the actual pinned local model, durable worker, stored-map
reopening and browser controls. The coordinating agent repeated the production
restart/recheck after the last lease-fencing guard. These checks do not establish
scientific usefulness or live PubMed coverage.

The implementation extends `MVPService`, its existing contracts and private
SQLite storage. Streamlit remains a reference interface. No parallel research
engine, formal-ledger promotion, Qwen-profile change, or personal-site deployment
is part of this checkpoint.

The final application was left running locally at `http://127.0.0.1:3000/`
against the separate durable `.mvp-web-state/` directory, with an empty
workspace list. Acceptance records remain in `/private/tmp/lre-v02-browser-state`
and were not migrated into it. Existing research data was not moved. The final
launcher used the production build and explicitly enabled the configured offline
local model; opening the landing page did not load model weights.

## Executed checks

The Python environments used Python **3.12.7**. The focused MVP environment has
Streamlit **1.66.0**; the optional web environment has FastAPI **0.153.0** and
Starlette **1.3.1**. Core/API providers were injected software fixtures or the
existing licensed offline example. A later explicit local embedding smoke is
recorded below. No live PubMed request or paid inference was performed, and the
embedding smoke attempted no network connection or model download.

| Check | Actual result | Scope |
|---|---|---|
| Initial existing MVP suite, before the draft fix | 114 passed in 3.74 s | Baseline execution in this cycle |
| Four new draft regressions against the original UI | 4 failed | Reproduced the navigation defect before fixing it |
| The same four regressions after the fix | 4 passed in 1.50 s | Received control values survive hidden-widget cleanup |
| Current focused MVP suite | **122 passed in 8.71 s** | Includes actual Streamlit AppTest checks; no skips |
| Combined current mapping/API suite | **109 passed in 20.33 s** | 83 mapping + 26 API; no skips; includes the independent cases below |
| Earlier independent HTTP/API run | **26 passed in 2.67 s** | Isolation, persistence, bounds, history, drafts and crash recovery; included in the current combined total |
| Independent API fault evaluation | **8 probe groups passed** | Temporary databases and real subprocess interruptions |
| Independent mapping cases | **48 passed** | Artifact/projection/window/cache/ranking fixtures; included in the 83 mapping cases |
| Independent durable-job cases | **7 passed in 1.03 s** | Actual worker-process interruptions, lease fencing, deletion/cancellation, backup/restore and rollback; included in the 83 mapping cases |
| Current frontend tests / TypeScript / production build | **17 passed / PASS / PASS** | Draft, bridge, viewport and map controls; no skipped tests |
| Relevant legacy suites | **220 passed in 4.76 s** | Retrieval, source documents and export compatibility; no skips |
| Frozen file bindings | **182 matched** | Byte sizes and SHA-256; manifests were not changed |
| Headless saved-example smoke | **PASS**, exit 0 | 9 reported, 1 fetched, full text, 5 passages; explicitly synthetic judgment |
| Core/auxiliary import check | **PASS**, exit 0 | No Streamlit, FastAPI, model stack or Chroma loaded |
| Real local embedding smoke | **PASS**, 6.374 s | 537 tokens in two complete windows; later worker/browser checks are recorded separately |
| Real worker/map/browser flow | **PASS** | Two stored singleton maps, two successful jobs, one reused embedding and unchanged research snapshot |

The API run reported two upstream dependency deprecation warnings for
Starlette/TestClient and AnyIO. The legacy run reported five existing PyMuPDF/SWIG
deprecation warnings; frontend hook tests emit upstream `react-test-renderer`
deprecation notices. One model-enabled server shutdown reported a
`resource_tracker` warning about one semaphore to clean up. This shutdown warning
remains unresolved; the subsequent integrity and reopening checks found no data
failure. No warning was counted as a skip. Earlier broad-suite
results, including the historical v0.1 skips in `mvp_evaluation.md`, were not
rerun or counted as current v0.2 coverage here.

### Exact test commands

```sh
/private/tmp/lre-mvp-venv/bin/python -m pytest tests/mvp/test_drafts.py -q
/private/tmp/lre-mvp-venv/bin/python -m pytest tests/mvp -q
/private/tmp/lre-web-venv/bin/python -m pytest tests/web_api -q
.venv-map/bin/python -m pytest tests/mapping tests/web_api -q
.venv/bin/python -m pytest tests/test_project_retrieval.py tests/test_project_retrieval_acceptance.py tests/test_project_retrieval_v3_acceptance.py tests/test_review_exports.py tests/test_review_documents_acceptance.py -q
```

The evaluation agent's earlier frontend checks used the bundled Node executable
explicitly, from `apps/web`:

```sh
/Users/hunt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --import tsx --test tests/*.test.ts tests/*.test.tsx
/Users/hunt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node node_modules/typescript/bin/tsc --noEmit
```

The final frontend agent run used the following commands from `apps/web`, with
`/Users/hunt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin`
prepended to `PATH`:

```sh
pnpm test
pnpm typecheck
NEXT_TELEMETRY_DISABLED=1 pnpm build
```

These produced 17 passing cases, a successful typecheck and a successful
production build (4.5 s). Generated API types were also refreshed successfully
with `.venv-map/bin/python scripts/export_web_openapi.py` from the repository
root, then `pnpm generate:api` from `apps/web`. No API shape changed afterward.
Initial `pnpm test` / `pnpm typecheck` attempts in the evaluation shell exited 1
because `node` was absent from its `PATH`; the explicit runtime commands resolved
that environment issue without changing dependencies. The evaluation agent's
earlier frontend run had 13 passing cases; the coordinating and frontend agents
reported the final 17-case run after the additional map controls landed.
Repeated runs and subset totals are not added together.

The before/after draft evidence is preserved locally in
`/private/tmp/lre-v02-checkpoint-a-before.txt` and
`/private/tmp/lre-v02-checkpoint-a-after.txt`. The baseline reproduction harness
runs the new tests against `app.py` extracted from `8df5993`, without reverting
the working tree. Current MVP, smoke, import and rehash output is in
`/private/tmp/lre-v02-checkpoint-a-final.txt`. These temporary files are local
execution evidence, not required installed application files.

## Publication verification — 21 October 2026

Before committing, the staged source tree was exported without unrelated local
files or private state. Its focused MVP run passed **122 tests in 5.53 s**, with
no skips. Its mapping/API run passed **109 tests in 20.08 s**, with no skips and
the same two dependency deprecation warnings. Commands ran from the exported
tree `/private/tmp/lre-v02-staged-skski0ml`:

```sh
/private/tmp/lre-mvp-venv/bin/python -m pytest tests/mvp -q
GIT_DIR=/Users/hunt/Desktop/lit-rev-engine/.git GIT_WORK_TREE=/private/tmp/lre-v02-staged-skski0ml /Users/hunt/Desktop/lit-rev-engine/.venv-map/bin/python -m pytest tests/mapping tests/web_api -q
```

The first archive-only mapping/API attempt passed 108 cases and failed the
baseline-reader case because `git show 8df5993:...` had no Git metadata. Supplying
the baseline Git context resolved it without implementation changes. The tests
still imported source from the exported staged tree. Frontend, browser, live
provider and real-model checks were not repeated during publication; their
implementation-time evidence remains above and below. The publication audit
confirmed unchanged implementation/test bytes, partial README/ignore staging,
and exclusion of private data and unrelated work.

## Draft fix and service compatibility

The Streamlit fix mirrors `research_question`, `pubmed_query` and
`passage_question` into a non-widget session dictionary and restores/detaches
those keys before routing. Tests demonstrate that an edited research question,
a submitted mocked-live query, a distinct submitted evidence question, and an
intentionally empty question survive Discover → Prepare → Evidence → Discover.
Navigation does not change research snapshots or call providers again.

This reference-interface fix preserves values received by the Streamlit server.
It does not establish hard-reload recovery or persistence of browser-only,
unsubmitted form typing. The new web application's persisted draft API has
separate version/CAS and assessment-head guards. The browser conflict discovered
later in this cycle was fixed and rechecked separately, as recorded below.

The bound retrieval operation checks the expected preparation/revision inside
the existing serialized service operation. Archived source reads resolve the
original run, preparation, bibliography and source integrity checks. Existing
CLI/service retrieval and export formats remain covered by the focused and
legacy checks. Tests also back up a copy of the domain database and read it with
the baseline storage reader, retaining IDs, source hashes and assessment text.

## Independent API and fault review

The first independent fault probes found three defects: a draft-head check/write
race, an orphan domain workspace after a registry binding failure, and a
concurrent-delete rollback that could remove a successful deletion's tombstone.
These were fixed before the final evaluation.

The final independent command was:

```sh
/private/tmp/lre-web-venv/bin/python /private/tmp/lre-v02-api-final-evaluation.py
```

Its script and output are retained at
`/private/tmp/lre-v02-api-final-evaluation.py` and
`/private/tmp/lre-v02-api-final-evaluation.txt`. The eight passing probe groups
verified:

1. A concurrent assessment waits for the serialized draft publication; a later
   stale-head autosave returns 409 and leaves the prior draft intact.
2. Concurrent deletions clear the domain once, retain the tombstone, reject late
   auxiliary writes and allow an authorized idempotent retry.
3. Failed registry reservation/publication cannot produce a new inaccessible
   domain identity; restart and retry publish the reserved ID.
4. A real process exit before domain creation preserves the reserved ID on retry.
5. A real process exit after domain creation preserves the same ID and one domain row.
6. A real process exit before domain clearing remains retryable after restart.
7. A real process exit after domain clearing completes draft/binding cleanup on retry.
8. `clear_if_present` rejects a wrong capability for an existing workspace and
   safely repeats a valid clear.

The API suite additionally checks session isolation across reads, drafts,
searches, assessments, context, exports and deletion; cookie expiry/restart;
exact Host/Origin and CSRF requirements; request/draft limits and CAS rollback;
private storage permissions; source-history guards; unchanged audit schema; and
credential exclusion from responses, exports and generated OpenAPI. The web
bridge's initially unbounded request buffering was also replaced with a 1 MiB
streamed-byte limit, covered by the passing frontend tests. Frontend results are
not counted in the Python totals above.

No residual API blocker was found in this inspected and tested scope. This is a
focused local acceptance review, not a complete security audit or a hosted-service
security claim.

## Independent map and durable-job evaluation

The 83 mapping cases in the final combined run include the evaluation agent's
48 cases in `tests/mapping/test_independent.py` and seven in
`tests/mapping/test_independent_jobs.py`. The other mapping cases belong to the
implementation agent. These are software acceptance tests, not relevance labels
or research findings.

The independent artifact/projection tests exercise 0, 1, 2, 19, 20 and more
papers; identical and rank-deficient vectors; duplicate metadata; invalid, zero,
non-finite and very large finite vectors; input/profile/vector/coordinate
digests; exclusion counts; and atomic rejection of inconsistent publication
metadata. NumPy/UMAP run on explicitly synthetic vectors. A synthetic tokenizer
and encoder verify complete disjoint token windows, special-token handling and
weighted pooling without loading model weights. Neighbor tests deliberately
make the 2D positions misleading and verify that ranking uses original-vector
cosine similarity with stable ties.

The independent durable-job tests additionally verify:

- A real worker subprocess exits during synthetic embedding. Restart acquires
  the released OS lock, recovers the interrupted attempt and stops after the
  recorded attempt limit, without publishing an artifact.
- An expired attempt cannot finish a job, and a superseded attempt cannot
  publish or overwrite a newer attempt.
- Evidence reads and an explicit assessment save remain available while a
  synthetic embedding operation is blocked. Cancellation and deletion prevent
  late publication; deletion also prevents late cache writes.
- A quiescent backup/restore of the registry, research and map SQLite databases
  retains the authorized workspace, research snapshot, source and assessment
  hashes, artifact/coordinate digests and cached vector hashes.
- A publication quota failure rolls back the map and vector links atomically;
  the research sources remain readable.

This review found and verified fixes for duplicate exclusions, incomplete
embedding-window metadata validation, large-vector normalization overflow,
inconsistent artifact publication metadata and an expired-attempt failure path
that initially lacked lease fencing. No failing case remains in the final
combined run. Concurrency/crash fixtures use synthetic papers and vectors; they
do not make extra model or provider calls.

## Real browser workflow

The coordinating agent executed this flow in a real local browser, separately
from AppTest and TestClient. These IDs are record identities, not access secrets:

| Record | Observed ID |
|---|---|
| Workspace | `17118719-fa18-4098-b3b8-05e18e46d3dd` |
| Saved search | `57a921b8-552e-4e6d-9a6f-aebe394ba130` |
| Initial preparation | `c6025f63-d0d9-4ba3-b320-be2aea6bba30` |
| Initial evidence run | `4dd7fcd5-dd8a-44cc-bbb3-17eb9abb71f2` |
| Current run after explicit source refresh | `5e3be812-6373-4217-8f99-c03a241e472b` — source revision 2 |

Observed actions and outcomes:

- Created an offline workspace, searched the labeled saved example, prepared
  permitted full text and retrieved five passages.
- Inspected the exact source anchor `[0, 1518)`.
- Submitted an incomplete partial-support judgment: HTTP 422 preserved the draft.
  Added missing information, saved, and explicitly revised it, producing a
  two-record immutable assessment chain. These were software-test judgments.
- Downloaded audit JSON through the actual browser: HTTP 200. The final
  production browser check also downloaded `/Users/hunt/Downloads/evidence.csv`:
  10 passage rows, 42 columns, SHA-256
  `2be39ace985f24be1913ca25eae0ccd61005af08ff5997353a9a4e52d3d89031`.
  It includes the synthetic software-test judgments and historical/current runs;
  it is not a scientific evidence assessment.
- Stopped and restarted both servers, closed/reopened the browser tab, and
  reopened the same workspace and saved records.
- Explicitly refreshed sources and opened the original evidence as read-only
  history with **ARCHIVED SOURCE BINDING**.

The initial browser run exposed a false older-assessment-head draft conflict
after rapid Save → navigation. The acknowledged assessment baseline is now
persisted before navigation. A new frontend regression passes, and the
coordinating agent repeated Save → immediate History → Evidence, then Revise →
Save → immediate History → Evidence → hard reload. The current revision's notes
were retained, the draft displayed **saved**, the committed assessment reopened
read-only, and no false conflict appeared.

A separate real-browser two-tab conflict check also passed. Both tabs loaded the
same current run and entered revision mode. Tab 6 saved draft B; tab 5 then showed
**Draft: conflict — newer saved draft exists** while retaining its local notes,
`Synthetic concurrent draft A.` Source inspection remained available in both
tabs and created no assessment. This is browser evidence for a genuine 409 path,
separate from the mocked hook and API tests.

On desktop, all five matching passage/judgment row Y coordinates were equal.
Computed colors matched paper `#f7f6f2` and accent `#667358`. At **390 × 844**,
the document's `scrollWidth` was **390** and each passage ended above its matching
judgment. These are new React browser measurements, separate from older
Streamlit checks. A separate complete keyboard/reduced-motion browser audit was
not reported for this checkpoint; source code and existing presentation tests
are not a substitute for that manual audit.

The coordinating agent accepted checkpoint A's offline gate after this recheck.

## Headless and frozen preservation

The current saved-example smoke command was:

```sh
/private/tmp/lre-mvp-venv/bin/python scripts/mvp_smoke.py --output /private/tmp/lre-v02-evaluation-smoke-230a4ba141e34b399402c5d81b886da8 --save-example-judgment
```

It wrote `evidence.csv` and `audit.json`, validated each exact-source anchor,
reported `streamlit_imported: false` and `paid_inference_calls: 0`, and labeled
its uncertain judgment synthetic. A separate fresh-process import of
`src.mvp.service` and `src.mvp.workspace_ui` confirmed that `streamlit`, `fastapi`,
`torch`, `transformers`, `sentence_transformers` and `chromadb` were absent from
`sys.modules`.

The final rehash compared every pinned file's bytes and size:

| Manifest | Bindings | Result |
|---|---:|---|
| `qwen-components-confirmation-freeze-v1.json` | 75 | MATCH |
| `qwen-components-development-freeze-v1.json` | 72 | MATCH |
| `qwen-kaggle-freeze-v2.json` | 35 | MATCH |

No frozen expected values were rewritten. The unrelated local benchmark,
research data and historical artifacts are outside this checkpoint's changes.
The coordinating agent also compared 145 preexisting files against the
pre-checkpoint preservation inventory. They matched after removing only the
authorized additive README and `.gitignore` blocks; scope files and private
research data remained unchanged. The complete change inventory is recorded in
[mvp_v0_2_changed_files.md](mvp_v0_2_changed_files.md).

## Opt-in real local embedding smoke

The coordinating agent ran, and the evaluation agent inspected the resulting
JSON from:

```sh
.venv-map/bin/python scripts/mvp_map_smoke.py --allow-local-model --output /private/tmp/lre-v02-real-map-smoke
```

The first integration attempt failed because the installed Transformers 5.12.0
tokenizer no longer supported `prepare_for_model`. The adapter was repaired
before the successful smoke; the initial failure is not counted as a pass.

Observed result in `/private/tmp/lre-v02-real-map-smoke/result.json`:

- Real `BAAI/bge-small-en-v1.5` model/tokenizer revision
  `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, local-files-only and no remote code.
- Actual saved PMID `42051515`: **537 tokens**, window weights **[510, 27]**,
  all tokens accounted for, **384** vector dimensions and unit norm **1.0**.
- One honest saved coordinate **[0, 0]**, `none_single_paper`, no invented neighbors.
- **0 network connections attempted, 0 model downloads, 0 paid inference calls**
  during the smoke; elapsed time **6.374 seconds**.
- Runtime versions, exact model/tokenizer file hashes and the profile are in
  the result; profile SHA-256 is
  `a1a78133b8491cdadc8dc2a95546a6bb0457d59040013072ffc95fca4c99991f`.
  `artifact.json` is retained beside the result.

This smoke proves the direct local adapter and artifact path for one saved
paper. Worker persistence and browser acceptance were checked separately below.
It does not prove multi-paper embedding quality or a live search. Independent
multi-point projection tests use synthetic vectors.

## Real worker, persisted map and browser acceptance

The coordinating agent exercised the optional local-model worker through the
local web application. The initial jobs ran with the Next development server;
the final reopening and reuse checks ran against the production build. The
saved example has one actual article, so the
honest map contains one point at **[0, 0]** and no other-paper neighbors. The
browser did not display a synthetic multi-paper demonstration as research data.

| Record | Observed ID |
|---|---|
| First job | `bcb70bd2-a84b-4deb-8474-6c96f14c77e0` — succeeded, attempt 1 |
| First map | `47ec3e1b-b35b-445b-b8ca-3c7d33df6db2` |
| Explicit rebuild job | `b63a3f41-bdc1-4689-be35-a4467ca38ee1` — succeeded, attempt 1 |
| Rebuilt map | `bf99b86e-d01d-45a9-8614-61c36409b94e` |

The browser verified filtering to zero points and restoring the point, selecting
the paper, opening its inspector with keyboard Enter, syncing inspector/list
selection and reopening its existing preparation. Pan, zoom, reset and History
navigation preserved the saved artifact. At a **390-pixel** viewport, the
document width remained **390** and the map width was **342**. The Map/Papers
toggle worked; zoom **1.3** survived Papers → keyboard Inspect → Map, with the
inspector visible outside the panels.

Both servers were stopped and restarted, and the original browser tab was
closed. A new tab opened the first saved map without refitting. The private
database proof retained **two maps, two succeeded jobs and one shared
embedding**, with an unchanged research snapshot. The first map's artifact
SHA-256 remained
`dd11508f837db7bcb1124803f9e92d802786a9591da113d7a2f3b8e866a01efe`;
its coordinate SHA-256 remained
`825626721dc3485855373d9948a9f8f6314d983897a8980af95f8d0a9b9f9466`.
The proof records `research_snapshot_unchanged: true` and `restart_refit: false`.

Local evidence is retained in
`/private/tmp/lre-v02-map-before-navigation.json`,
`/private/tmp/lre-v02-map-final-browser-proof.json` and
`/private/tmp/lre-v02-map-browser.png`. The evaluation agent inspected the final
proof's map/job counts, identities and integrity hashes. The coordinating agent
performed an additional production restart after the final lifecycle/lease
guard changes, hard-reloaded the old map and called Create or reuse. That call
returned the existing rebuild job/map; the two-map, two-job, one-embedding counts
were unchanged. Both checkpoints were then accepted for this offline scope.

The final production launch used the existing model cache in offline mode:

```sh
MVP_MAP_ENABLED=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv-map/bin/python scripts/run_web.py --production --node /Users/hunt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --data-dir /private/tmp/lre-v02-browser-state
```

The browser used `http://127.0.0.1:3000` and the private API used port `8765`.

## Release status

| Area | Status | Evidence boundary |
|---|---|---|
| v0.2a workspace parity | **ACCEPTED — offline local gate** | Core/API, browser flow and rapid-save conflict fix checked |
| Reopening | **TESTED, local same browser** | Real server restart/tab reopen and API identity checks |
| Durable drafts | **TESTED — local scope** | API CAS/crash tests and final browser save/navigation/reopen sequence pass |
| v0.2b semantic map | **ACCEPTED — offline local gate** | 83 mapping tests, actual local worker, stored-map reuse/restart and browser controls |
| Real embedding integration | **TESTED — one saved paper** | Actual pinned local model, full 537-token input, durable worker and browser; no multi-paper scientific benchmark |
| Live PubMed end-to-end | **NOT_RUN** | No approved live provider execution in this cycle |
| Scientific map/retrieval benchmark | **NOT_RUN** | No human-labeled multi-paper benchmark or measured review usefulness in this cycle |
| Legacy/frozen preservation | **TESTED** | 220 relevant legacy cases and 182 matching bindings |
| Hosted deployment | **OUT_OF_SCOPE** | No publication, deployment, merge or push performed for these checks |

The demonstration remains one real article from a preserved, curated Europe PMC
preview: nine reported matches and one fetched article. It does not demonstrate
a multi-paper semantic landscape, complete literature coverage, retrieval
usefulness for the proposed review, or independent human verification.
