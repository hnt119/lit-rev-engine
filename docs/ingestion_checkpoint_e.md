# Checkpoint E — exact spans, board integration and measured development results

Implemented locally on `codex/mvp-v0-3`, HEAD `551068a16741820fe316b5027b5b181f4e0c9770`.
The [ticket and interface plan](ingestion_checkpoint_e_plan.md) records ownership,
budgets, frozen inputs and acceptance decisions. No dependency/version changes,
commits, pushes, merges, deployments or private-data publication were made.

## What works

B1 fixes the full-block-ranking / prefix-delivery mismatch with contiguous,
query-aligned lexical windows. Scores use exactly the delivered quotation.
Sentence boundaries, explicit hard-boundary warnings, bounded overlap and stable
ties keep offsets reproducible. Retrieval remains one paper × one field, with
optional explicit component queries. Components guide retrieval; they do not
replace the extraction question, inspect a source or establish support.

Choose B0 or B1 explicitly when creating or revising a board in the new UI.
Old API requests retain the exact B0 defaults and fingerprints. A B1 definition
cannot silently downgrade through an old implicit-profile revision request.
Maps and paper embeddings are untouched. Existing passage retrieval profiles,
assessments, historical references and exports remain intact.

The new candidate receipt is `mvp.board-candidates.spans.v2`. It records exact
original code-point ranges, omitted-before/after context, lexical component
counts, block/window scope, incomplete indexing, runtime and the declared budget
tokenizer. Original source locators are reconstructed on the server. Replayed
receipts are checked against their immutable record and canonical quotations.
Source totals, selected ownership, ranks, exact proxy budgets and consistency of
all count metadata are validated. A lexical match never proves whole-paper
absence, participant eligibility or semantic support.

Ranking receives independent captured copies and runs outside mutation,
lifecycle and SQLite guards. Publication rechecks the definition, source,
profile, ownership and deletion state; invalid/stale results roll back. The CPU
gate admits one active span search per process. The eight-second deadline is
cooperative rather than hard process preemption. At most 2,048 blocks, 8,192
windows and 4,000,000 source code points are indexed; omissions are explicit.
At most three quotations, 3,600 characters / 1,200 lexical budget units are
delivered per paper/field, with 1,200 characters / 400 units per quotation.
These are not measured model tokens.

Optional proposals reuse the existing disabled-by-default local adapter, prompt,
generation budgets, review/adoption and submission workflow. B1 has an explicit
`primary-spans-round-robin.v1` packet policy. Only exact primary quotations enter
the unchanged packet-v1 context meaning; v2 window diagnostics stay in the
referenced candidate receipts and retrieval-profile digest. Reserve one available
candidate per field, deduplicate exact shared anchors, then add whole extra
quotations round-robin. Fail before generation if the initial coverage set cannot
fit the existing byte/character limits. Legacy packet construction is unchanged.
Software mocks produced nine proposals across three papers/three fields without
automatically writing any cell head, draft value or human judgment.

## Fixed-source development comparison

Manifest: `tests/fixtures/span_retrieval_v1/manifest.json`, SHA-256
`437888582ab4fb82ee647b24b4e40f9a2c1ca9b4ff34a5bd6120fa28fb81390e`.
Eleven sources / twelve paper-field cases: eight synthetic sources, three
licensed public-pack sources, ten answerable cases and twenty-one exact anchors.
The labels were frozen before reading B1 ranks. All eleven related-study groups
remain development data. Table qualifier cases are synthetic; public cases use
paragraph anchors. Cross-report relatedness has not been human-adjudicated.

| Lane | Exact anchors | Complete answerable component packets |
|---|---:|---:|
| B0 unchanged question / block-prefix delivery | 12/21 | 5/10 |
| B1 identical full field question / exact windows | 15/21 | 6/10 |
| B1 additional explicit component queries | 21/21 | 10/10 |

The mandatory late-block case improved from 0/3 to 3/3 anchors. Question-only B1
had no per-case regression; public question-only anchors stayed at 3/6. Its
remaining misses include population/affiliation distinctions, a table footnote
and public-source components. Extra explicit queries recover those development
anchors, but that gain cannot be attributed solely to windowing.

All five recorded gates passed: exact identity/quotation/budget checks, complete
indexed scope for the bounded fixtures, mandatory late recovery, the explicit
component target on mandatory synthetic cases, and no duplicate or overlap ≥
half the shorter quotation. The separately recorded per-case regression list is
empty. Native budget
violations, evaluator-only transport clips, smaller overlap and index omissions
were all zero in these cases. Maximum delivered context was 2,840 characters /
533 proxy units; total measured ranking time over 36 outputs was 0.05027 seconds,
maximum single-case 0.00742 seconds. These small development timings are not a
production latency guarantee. The public browser below demonstrates that smaller
overlap can occur outside these fixtures.

Both insufficient-context cases returned candidates in every lane (2/2). This
is not an unsupported-claim rate: no answer was generated. Complete packets are
engineering anchor coverage, not supported-cell completion or independent
human judgments. The requested ten-percentage-point supported-cell goal,
unsupported answers, useful abstention, correction time and competitive
performance are **not measured**. Do not advertise superiority or call these
fixtures human-reviewed/held-out evidence.

The initial comparison receipt remains retained. A behavior-identical extraction
of the pure budget tokenizer changed code hashes, not the profile hash or ranks.
The final receipt pins all code/input/profile hashes and all 36 actual outputs.
No rank-informed fixture/algorithm tuning or dense/reranker addition followed.

```sh
/private/tmp/lre-mvp-venv/bin/python scripts/evaluate_board_spans.py \
  --output .mvp-web-state/ui-checks/ingestion-rag-2026-10-21/span-development-final.json
```

Human adjudication template:
`tests/fixtures/span_retrieval_v1/human_adjudication_template.csv`.
The split/relatedness policy is in `split_manifest.json`; no held-out group is
invented. Real local proposal evaluation requires separate authorization and an
explicit pinned endpoint/model. No provider or paid fallback was enabled.

## Fresh software checks and failures

```sh
/private/tmp/lre-mvp-venv/bin/python -m pytest tests/mvp -q -rs
# 689 passed, 0 skipped, 36.54 s
.venv-map/bin/python -m pytest tests/mapping tests/web_api -q -rs
# 227 passed, 0 skipped, 77.16 s; two existing dependency deprecations
cd apps/web
/Users/hunt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --import tsx --test tests/*.test.ts tests/*.test.tsx
# 121 passed, 0 failed/skipped, 2.174 s (final post-copy rerun)
/Users/hunt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node node_modules/typescript/bin/tsc --noEmit
# passed
# Production build used the copied app at /private/tmp/lre-ingestion-browser-A/apps/web:
NEXT_TELEMETRY_DISABLED=1 /Users/hunt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node node_modules/next/dist/bin/next build
# passed; TypeScript and static generation completed
```

TypeScript, production build with `NEXT_TELEMETRY_DISABLED=1` and diff checks
pass. A fresh temporary-app OpenAPI projection also matches the retained
72-path schema exactly. Root independently recomputed all 36 outputs' canonical
quotations and anchor coverage from their actual retained inputs; totals match
the comparison table. Counts include the 44 independent E checks (21 pure and 23 HTTP), the 21
retrieval unit checks, three new board checks and fourteen packet/proposal
checks; these subsets are not additional observations. Models and transports
are mocked. No real embedding/generation is hidden in these results.

Independent evaluation exposed genuine integration defects: inconsistent
block/count metadata and understated proxy budgets were initially accepted;
strict token validation then escaped as HTTP 500; internally consistent forged
source character/block totals could publish. They now fail with controlled
errors and no artifact. Fourteen malformed-output cases and five unlocked
CPU/stale/refresh/delete/tombstone/source-tamper cases pass. Ownership,
canonical quotation, replay, inspection, downgrade, history and export checks pass.

Test-harness errors were also corrected and kept separate: synthetic canonical
fixtures must not pretend to retain raw JATS bytes; an anchor beyond 1,200 need
not imply the window starts beyond 1,200; source type is binding metadata;
history uses the frozen `items` key; frozen DTO tampering uses copied constructed
values; proposal profile binding is checked through the actual retrieval-input
digest. No frozen source labels changed. A browser copy issue was corrected:
the shared busy flag no longer labels source retrieval/inspection as
“Submitting…” on the separate submit action.

## Actual browser acceptance

Isolated production UI `http://127.0.0.1:3003`, API `8767`, separate public QA
data directory. Only those known test processes were restarted. The normal
research instances/data were not used for browser mutations; external
credentials and generation were disabled in the acceptance harness.

New board `9b6cbb44-2ce2-4959-9308-8b67ed8d16bb` uses the current retained C
collection preparation: two actual licensed public full texts and one imported
abstract. The preexisting C board and its revisions were left intact.

- Explicitly selected B1 and three retrieval components for Population; Study
  design and Exposure retain their exact full subquestions as defaults.
- Retrieved each of the nine paper/field cells separately: six full-text cells
  returned three spans each; the abstract returned two, one and two. All UI
  source/index/omission/proxy-token labels were visible.
- Inspected population range 573–1614 of a 2,531-code-point canonical XML
  paragraph; the exact highlighted range was 1,041 code points. The source
  retained its original XML path/section locator and showed earlier/later context
  separately. Its retrieval has 197 smaller-overlap characters between two
  quotations; this is below the dedup threshold and remains delivered context.
- Inspected another real full text at 2554–3113, beyond the old prefix. This is
  a narrative review discussing a cited study; an intact quotation does **not**
  establish the review's own study design. No support judgment was assigned.
- Saved a clearly labeled software-only manual value/reference/inspected range;
  reloaded to confirm the draft survived; explicitly submitted, explicitly
  revised, and loaded both immutable revisions with the original anchor intact.
- Inspected the imported abstract's exact binding; recorded a null awaiting
  human exposure review with explicit missing information and no whole-paper
  absence claim. No scientific value or support was automatically set.

<!-- final-browser-export-evidence -->

- Reopened the submitted abstract-only record after the final production rebuild.
  Downloaded an actual 18,215-byte CSV (nine cells) and 163,981-byte audit JSON:
  one collection-board definition, nine v2 span retrieval receipts, three
  immutable cell revisions and two submitted heads. The explicit revision
  supersedes its original; the abstract value is JSON null with one inspected
  range. All judgments remain unassessed and all range lengths match exact
  code-point offsets. Existing collection-board table/audit schemas stay v2.
- Read-only comparison against the original C download confirmed its three
  cell revisions, two legacy candidate receipts, definition and two heads are
  unchanged. The new board does not replace that earlier board.
- Expanded optional AI controls and verified “GENERATION DISABLED”, the existing
  nine-cell/three-call bounds and disabled generation action. No model action
  was requested. The final rebuilt UI also kept retrieval/inspection separate
  from the explicit submission label.

These are software workflow checks, not human research usefulness validation.
New live PubMed/provider calls, real embeddings, local generation, human
adjudication and held-out evaluation remain `NOT_RUN`.

## Preservation, startup and next decision

The final independent audit assigns 40 original files to this task and verifies
all 685 other original hashes unchanged. It preserves the failed earlier
688-file comparison and explains the three authorized scope additions: final D
History copy, E board routes and E proposal dispatch. All 1,069 original rows,
28 table hashes and safety-copy tables remain unchanged; zero appends, changes
or deletions. Branch/HEAD and `main` remain unchanged.

Use the existing [web/API startup](mvp_v0_3.md#run-locally) and
[Streamlit startup](manual_comparison_board.md) with the existing data directory.
Restart those normal processes to load the new source. The running 3003/8767
walkthrough uses separate public QA state. Keep generation disabled unless
explicitly configuring and authorizing it. No database replacement is needed.

Decision: retain this inexpensive explicit span option. The next evidence gate
is reviewer adjudication of source-first cases, related-study split review and
a separately authorized matched local-model evaluation of field answers. Do not
add dense retrieval/reranking or claim a RAG product advantage on current labels.

## Exact changed files since checkpoint D

42 paths changed against the final D source freeze. The final A–E source freeze
contains 146 task-owned files; unrelated files and private acceptance outputs are
excluded. The private receipt records every final SHA-256 and actual command.

<!-- checkpoint-E-file-list -->

- `apps/web/components/board-candidates.tsx`
- `apps/web/components/board-retrieval-profile.tsx`
- `apps/web/components/compare.tsx`
- `apps/web/components/workspace-app.tsx`
- `apps/web/lib/generated-api.ts`
- `apps/web/lib/openapi.json`
- `apps/web/tests/board-spans.test.tsx`
- `apps/web/tests/discover-selection.test.tsx`
- `apps/web/tests/import-collection-fixtures.ts`
- `apps/web/tests/inspector-navigation-independent.test.tsx`
- `apps/web/tests/map-navigation.test.tsx`
- `apps/web/tests/map-selection-integration.test.tsx`
- `apps/web/tests/offline-example.test.tsx`
- `apps/web/tests/preparation-jobs.test.tsx`
- `apps/web/tests/query-suggestions.test.tsx`
- `docs/ingestion_checkpoint_d.md`
- `docs/ingestion_checkpoint_e.md`
- `docs/ingestion_checkpoint_e_plan.md`
- `docs/ingestion_rag_checkpoints.md`
- `scripts/evaluate_board_spans.py`
- `src/mvp/adapters/board_storage.py`
- `src/mvp/adapters/span_packets.py`
- `src/mvp/adapters/span_retrieval.py`
- `src/mvp/cell_proposals.py`
- `src/mvp/evidence_board.py`
- `src/mvp/span_board_contracts.py`
- `src/mvp/span_budget.py`
- `src/mvp/span_evaluation.py`
- `src/mvp/span_retrieval_contracts.py`
- `src/web_api/app.py`
- `src/web_api/board_routes.py`
- `src/web_api/contracts.py`
- `tests/fixtures/span_retrieval_v1/README.md`
- `tests/fixtures/span_retrieval_v1/SHA256SUMS`
- `tests/fixtures/span_retrieval_v1/human_adjudication_template.csv`
- `tests/fixtures/span_retrieval_v1/manifest.json`
- `tests/fixtures/span_retrieval_v1/split_manifest.json`
- `tests/mvp/test_span_boards.py`
- `tests/mvp/test_span_packets_unit.py`
- `tests/mvp/test_span_retrieval_independent.py`
- `tests/mvp/test_span_retrieval_unit.py`
- `tests/web_api/test_board_spans_independent.py`
