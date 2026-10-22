# Practical ingestion and evidence retrieval checkpoints

Implementation baseline: `codex/mvp-v0-3` at
`551068a16741820fe316b5027b5b181f4e0c9770` (21 October 2026).
The manual comparison board and optional, disabled-by-default AI proposals are
already implemented. Their historical evaluation results are not fresh results
for this work. Main, unrelated working files and private research are preserved.

## Ordered tickets and acceptance

| Checkpoint | Deliverable | Gate |
|---|---|---|
| A | Filtered inspector Previous/Next; shared 30-paper selection contract; typed bounded selection drafts | Navigation has no preparation, selection, map-refit or generation side effects. The 31st choice preserves the first 30. Legacy synchronous preparation stays bounded at ten. |
| B | Persisted preparation jobs, per-paper staging/progress, cancel/restart, short atomic publication | Fetch/parse outside workspace mutation locks; current sources retained until publication; stale/deleted/cancelled attempts cannot publish. Measure 30-source storage and refresh. |
| C | Zotero CSV, compatible RIS and DOI import; immutable origins and collections | Parse/preview/resolve/review/commit is explicit; imported and combined collections work through Explore, Prepare, Evidence and Compare without fabricated search history. |
| D | Editable structured search plans, deterministic compiler and explicit query diagnostics | Preserve specialist strategies and required/deferred/excluded intent. No provider or model calls during typing or navigation. |
| E | Versioned query-aligned exact spans and controlled retrieval evaluation | Fix late-block prefix loss without changing legacy/frozen profiles; distinguish engineering tests, real inference and human usefulness. |

Implementation, retrieval and independent evaluation tickets have separate file
ownership. Root owns contracts, architecture, acceptance decisions and the next
ticket. No new dependencies are required for A or the initial B worker; retain
the pinned Next/React/FastAPI/Pydantic stack.

## Evidence status

A passed the [recorded software and browser checks](ingestion_checkpoint_a.md).
B passed its [durability, storage and browser checks](ingestion_checkpoint_b.md).
C passed its [import, collection, compatibility and browser checks](ingestion_checkpoint_c.md).
D passed its [revision, compiler, concurrency, audit and browser checks](ingestion_checkpoint_d.md).
E passed its [software, browser and development-retrieval checks](ingestion_checkpoint_e.md);
the [interface/evaluation plan](ingestion_checkpoint_e_plan.md) records its limits.
Source-first human adjudication, a true held-out set and separately authorized
real-model answer evaluation remain pending. The development anchor gain is not
evidence of supported-cell completion or competitive superiority.
Thirty-source execution is available through the ready job
worker; the synchronous path remains bounded at ten. No new live provider,
embedding, generation or human-usefulness result is claimed. Real local
generation evaluation requires separate authorization;
there is no paid or remote fallback. No commit, push, merge or deployment is
authorized for this implementation cycle.

## Startup

Use the existing [local web startup](mvp_v0_3.md#run-locally) and
[Streamlit instructions](manual_comparison_board.md). Keep the existing research
data directory. Tests use temporary databases and synthetic transports; do not
replace a private database with a test fixture.
