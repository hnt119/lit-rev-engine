# MVP v0.3 checkpoint guide

Checkpoint 0 extends the actual v0.2 implementation at `404b002` on local branch
`codex/mvp-v0-3`. It adds an opt-in saved-case audit and fixes a rapid source
selection bug. Subsequent corrections add the
[30-paper offline example and saved map](offline_example.md),
[compact PubMed keyword proposals](query_suggestions.md), and
[nearest-paper targeting and background-only panning](map_interactions.md).
The comparison board is the next checkpoint, described in the
[board plan](mvp_v0_3_board_plan.md); it is not implemented in this checkpoint.

The existing React/FastAPI workflow, Streamlit application, SQLite research
contracts, source permissions, passage retrieval, assessments, exports and
persisted maps remain the application. There is no new research engine or
generative inference requirement.

## Run locally

Use the installation steps in [the v0.2 guide](mvp_v0_2.md). The current checkout
has an isolated `.venv-map` environment with the optional pinned local map
dependencies. The command below assumes the frontend production build exists.

For the bundled offline example, the standard `.venv-web` API environment from
that guide is sufficient: no map model, NCBI contact or `MVP_MAP_ENABLED` flag is
needed. After building the frontend, run:

```sh
.venv-web/bin/python scripts/run_web.py --production --node /path/to/node \
  --data-dir .mvp-web-state
```

Use your installed Node executable. Configure the optional model environment only
when computing new maps. The following configured local command is for live
PubMed and optional model use, not a prerequisite for the offline example.

The application reads process environment variables. Merely placing
`NCBI_EMAIL` in `.env` does not load it into an already-running server. Export
the configuration before launching or restart after changing it. If using this
repository's trusted local `.env`, load it without printing its contents:

```sh
set -a
source .env
set +a
MVP_MAP_ENABLED=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv-map/bin/python scripts/run_web.py --production \
  --node /Users/hunt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node \
  --data-dir .mvp-web-state
```

Open `http://127.0.0.1:3000/`. Both servers bind to loopback. For another machine,
use its installed Node executable. Mapping requires the exact cached local
weights documented in v0.2; startup and viewing do not download them. Paid
inference is unused. Keep `.env` and the private state directory out of Git.

The existing local browser session expires after 30 days; clearing cookies loses
access. There are no named accounts or cross-device recovery claims. Keep the
current browser profile when reopening the case.

## Audit an explicitly named case

See [the case protocol](mvp_v0_3_case_protocol.md) for exact query approval,
selection, known-paper labels and rights boundaries. The generic
[protocol example](../examples/mvp/research_case_protocol.example.json) is
pending approval and contains no research source text.

```sh
.venv-map/bin/python scripts/mvp_research_case.py check \
  --protocol /absolute/private/path/protocol.json \
  --output /absolute/private/path/new-readiness-output

.venv-map/bin/python scripts/mvp_research_case.py audit \
  --protocol /absolute/private/path/protocol-with-selection.json \
  --data-dir /absolute/path/to/.mvp-web-state \
  --workspace-id WORKSPACE_ID --search-id SEARCH_ID \
  --preparation-id PREPARATION_ID --map-id MAP_ID \
  --output /absolute/private/path/new-audit-output
```

`check` validates readiness without requesting PubMed or loading a model.
`audit` checks original saved bindings, canonical source hashes, retained map
embeddings and stable reopening. It never captures or refits a case. Output
directories are new private directories; existing evidence is not overwritten.
These commands need the configured Python environment. Configuration flags
describe the audit process, not an independently inspected running server.

## Current private research case

The user-supplied workbook remains unchanged. Its concept expressions were
expanded without changing terms and checked independently against the workbook
XML. The first live preview uses its Asian coverage check, `UA = U AND A`, at
30 records. The broader `U` union and `Diet` subset are retained as planned
comparators, not executed searches; their overlapping counts must not be added.
This exploratory preview is separate from complete systematic-review capture.

The actual protocols, workbook hash/cell provenance, selection rationale,
capture/model receipts, original source state and screenshots stay under the
ignored local `.mvp-web-state` directory. The case-specific protocol directory
is `research-cases/workbook-2026-10-21/` within that private directory. It is not
a public demo or a redistributable fixture. No full abstracts, private queries
or source text were added to the public protocol example.

Fresh live/model/browser results and exact commands are recorded in the
[evaluation report](mvp_v0_3_evaluation.md). Software tests, provider execution,
actual local embeddings, source identity, human semantic judgments and human
usefulness are separate evidence categories. The provisional workbook pilot
does not supply a held-out relevance gold set. No human inclusion or support
judgments have been manufactured.

## Next checkpoint

Build the manual comparison board over retained sources, beginning with strict
contracts, small persistence and immutable definition revisions. Then add
bounded retrieval per paper/field, exact source inspection, durable cell drafts,
human submissions and separate board exports. See tickets B1–B6 in the board
plan. Optional structured extraction remains gated on that working manual
workflow and its independent evaluation.

This development checkpoint is maintained on
[`codex/mvp-v0-3`](https://github.com/hnt119/lit-rev-engine/tree/codex/mvp-v0-3).
The user authorized committing and pushing the reviewed implementation on
21 October 2026. Main is unchanged. Private captures, contacts, credentials and
supplied research materials remain local; the public offline pack was captured
separately from permitted sources. Historical evaluation sections describe their
execution-time state. Merging or deploying is outside this publication scope.
