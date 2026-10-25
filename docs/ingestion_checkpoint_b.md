# Checkpoint B — durable thirty-source preparation

Baseline remains `codex/mvp-v0-3` at
`551068a16741820fe316b5027b5b181f4e0c9770`; `main` remains at
`a506ae05fc19c21a1d80beabc26bfc831582441d`. Implemented and checked
21–22 October 2026. No commit, push, deployment, live scholarly request or
model inference was performed.

## Delivered and retained boundaries

Preparation is an explicit saved job. Its immutable input records the actual
search digest, ordered paper identities, expected source revision/preparation,
provider mode and request fingerprint. React submits a job for one to thirty
papers when the worker is ready. Streamlit uses the same job implementation
above ten papers; its existing synchronous path remains bounded at ten.

Provider fetch/parse runs outside workspace mutation locks and SQLite write
transactions. Per-paper outcomes and checksum-validated staged sources survive
restart. Progress/list/cancel do not wait for a legacy operation's workspace
flock. The previous current preparation remains usable until a short, atomic
publication checks search/source dependencies, cancellation, attempt ownership,
lease and runtime inside the research transaction. A failed publication rolls
back both its job-success status and research mutation.

One OS-locked worker owns preparation for an actual research database. Default
live HTTP transports additionally share bounded host rate gates across local
processes. Existing timeout, retry, identity, byte and rights checks remain in
place. No new dependencies or version upgrades were needed.

Bounds remain explicit: thirty prepared sources, ten board papers, sixty board
cells, nine proposal cells/three calls, twenty preparation jobs per workspace,
three restart attempts, 2,400 seconds of active job runtime, 32 MiB of
preparation auxiliary payload and 64 MiB of combined research/idempotency/job
payload. Mutable job metadata has an 8 KiB reservation. These are logical
payload limits; they do not describe peak process memory, WAL size or unlimited
refresh capacity. Cancellation is cooperative and cannot interrupt an HTTP
request already in progress; that attempt cannot subsequently publish.

## Fresh software execution

| Command/check | Actual result |
|---|---|
| `/private/tmp/lre-mvp-venv/bin/python -m pytest tests/mvp -q -rs` | Final complete run: **434 passed**, 35.18 s, zero failures/skips. |
| `.venv-map/bin/python -m pytest tests/mapping tests/web_api -q -rs` | Final complete run: **173 passed**, 74.59 s, zero failures/skips; two existing dependency deprecation warnings. |
| Bundled Node, `--import tsx --test tests/*.test.ts tests/*.test.tsx`, in `apps/web` | **77 passed**, zero skips. |
| Same Node, `--import tsx --test tests/preparation-jobs.test.tsx` | Final theme-only follow-up: **10 passed**, zero skips. |
| Same Node, `node_modules/typescript/bin/tsc --noEmit --incremental false` | Passed. |
| Same Node, `node_modules/next/dist/bin/next build`, isolated frontend copy with the existing shared theme | Passed for the job workflow; rebuilt after the final scoped progress-color adjustment. |
| `git diff --check` | Passed. |

Bundled Node is
`/Users/hunt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node`.
The full MVP run includes actual Streamlit AppTest execution of thirty saved
public full texts and restart/reopening, plus mocked transport tests of restart,
stage corruption, cancellation, deletion, stale dependencies, runtime/lease
expiry, idempotent historical replay and atomic rollback. The API run includes
session restart, CSRF, authorization, bounded projections and startup readiness.
An independent barrier regression holds the legacy workspace flock and confirms
job read/list/cancel each finishes before that flock is released.

An earlier broad mapping/API run had one failure: an existing map test wrote a
selection draft with the obsolete `paper_ids` key. Correcting that fixture to
the canonical `selected_paper_ids` preserved its original idempotency and
no-side-effect assertions. The final broad run above passes. React test renderer
also emits its existing deprecation notice; it is not a skipped test.

## Measured storage acceptance

The existing public thirty-paper offline pack supplies thirty permitted full
texts: 4,513,884 raw XML bytes and 6,487,162 serialized prepared-source bytes.
The storage test also retains an older one-paper preparation and evidence run.

| Bytes | Initial thirty-paper job | After explicit source refresh |
|---|---:|---:|
| Research snapshot | 13,249,075 | 19,737,005 |
| Saved idempotency results | 6,761,071 | 13,249,000 |
| Auxiliary payload including metadata reservations | 6,586,068 | 13,172,136 |
| Combined quota charge | **26,596,214** | **46,158,141** |
| Observed SQLite allocation | 26,677,248 | 53,039,104 |

Elapsed-time serialization can vary the logical totals slightly between runs.
Three exact reopen checks per phase retain quotations and CSV/JSON exports.
This measured workload fits the retained limits, so no blob migration, quota
increase or source-history discard was needed. Larger histories can reach the
declared limit and fail while leaving existing records readable.

## Actual browser execution

An isolated production Next.js UI/API used a temporary data directory and a
distinct session cookie. The existing research browser/session was preserved.
The browser used the actual public thirty-paper pack, not live requests.

1. Selected all thirty papers and submitted a job: thirty full texts published
   at source revision 1.
2. Submitted a refresh and cancelled it while queued: all thirty outcomes were
   cancelled and revision 1 remained current. A preceding attempt finished
   before the cancel click; it was recorded as completion, not cancellation.
3. Submitted another explicit refresh: thirty full texts published at revision
   2. Reloading retained all thirty selections, the receipt, source revision
   and unchanged saved-map transform.
4. Used the existing Evidence page to retrieve five passages from revision 2.
   Source inspection visibly highlighted the exact 748-character quotation.
   No human judgment, support rating or verification was assigned.
5. Downloaded both exports through the real browser controls: five CSV rows
   (14,520 bytes) and an `mvp.audit-bundle.v1` JSON export (20,593,932 bytes),
   retaining both thirty-source preparation revisions.

The private screenshot, downloads, measured receipts and disposable databases
remain outside versioned source. These checks establish software behavior, not
medical relevance, complete retrieval, real inference quality or human
usefulness. Live PubMed/Crossref, real embeddings, real generation and human
usefulness evaluation are **NOT_RUN** for this checkpoint.

The receipt screenshot precedes the final scoped olive progress-color fix. That
fix passed frontend tests and a production rebuild; the temporary browser tabs
were closed before a post-build color inspection could finish.

## Preservation audit

An independent comparison against the private baseline inventory and consistent
SQLite safety copies found **703 protected original files unchanged**, no
missing files, and **all 1,069 original database rows unchanged** across research,
board, map and web stores. There were zero draft updates/appends. Twenty-two
owned original A/B files changed. The inventory classification initially missed
the already-owned selection helper; correcting the allowlist did not alter data.
Original sources, board revisions, source bindings, maps, offline pack and
unrelated experiments were preserved. Branch, HEAD and `main` are unchanged.

## Changed files for B

```text
apps/streamlit/app.py
apps/web/app/globals.css
apps/web/components/discover.tsx
apps/web/components/preparation-jobs.tsx
apps/web/lib/bridge.ts
apps/web/lib/generated-api.ts
apps/web/lib/openapi.json
apps/web/tests/preparation-jobs.test.tsx
docs/ingestion_checkpoint_b.md
docs/ingestion_rag_checkpoints.md
src/mvp/adapters/preparation_storage.py
src/mvp/adapters/provider_rate_gate.py
src/mvp/adapters/storage.py
src/mvp/adapters/transport.py
src/mvp/local_preparation.py
src/mvp/ports.py
src/mvp/preparation_contracts.py
src/mvp/preparation_jobs.py
src/mvp/service.py
src/mvp/workspace_ui.py
src/web_api/app.py
src/web_api/preparation_routes.py
tests/mapping/test_jobs.py
tests/mvp/test_local_preparation_runtime.py
tests/mvp/test_preparation_jobs_independent.py
tests/mvp/test_streamlit_preparation_jobs.py
tests/web_api/test_preparation_jobs_independent.py
```

## Startup and remaining limits

Follow the [existing local web startup](mvp_v0_3.md#run-locally), rebuilding the
frontend and restarting the API. The normal API lifespan starts the job worker;
`preparation_jobs_ready` reflects actual worker ownership. Streamlit uses the
existing command and binds its private worker capability only after validating
the supplied workspace handle. Keep the existing data directory. Do not run
multiple independent provider-owning profiles against a copied database.

At this checkpoint jobs are search-bound. Import/collection-bound jobs and exact
abstract-origin provenance belong to C. UI polling is bounded and offers an
explicit resume action after interruption; polling never initiates preparation.
No live provider behavior or real model performance has been inferred from the
offline and mocked checks. No commit, push, merge or deployment is authorized.
