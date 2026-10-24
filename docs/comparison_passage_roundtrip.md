# Comparison → passage search → exact cell source

**Historical working-tree evaluation.** This report records the uncommitted
workflow checkpoint and its earlier archive, not the frozen committed release.
For the source freeze and publication boundaries, see
[preview .2 release notes](releases/v0.3.0-local-preview.2.md). Use only the later
archive rebuilt from that committed source SHA; the hashes below are retained
historical evidence and must not be used for publication.

This focused working-tree checkpoint extends the existing manual comparison and
passage-search pages. It does not change retrieval ranking, board retrieval
profiles, source preparation, assessment contracts or existing export schemas.
The source baseline is `02fa59fc9fafb8550354d64b696d1c7262d3924f` plus the retained
uncommitted local-preview and portfolio-overlay work. Nothing is published.

## Researcher workflow

1. Open a saved comparison. **Search passages for this comparison** prefills the
   board question and resolves its exact revision, preparation and paper set.
2. Alternatively, open a cell. Its existing inline **Find relevant passages**
   operation remains available. **Open passage search for this field** prefills
   that field's subquestion and limits the corpus to that cell's paper.
3. Edit the question and choose 5–30 passages. Navigation does not execute a
   search. **Retrieve passages** explicitly creates a run using the existing
   lexical ranker after restricting the corpus.
4. Use **Back to comparison** / **Back to cell**, or open a result in the cell
   inspector. The latter uses an authorized server reconstruction of the exact
   retained passage; URL parameters only identify records.
5. Reading a passage changes no cell value, references, support judgment or
   submitted revision. Explicit inspection/attachment and submission remain the
   existing manual operations. Editing an already submitted cell still requires
   **Edit saved cell**; navigation does not begin a revision.

Empty or abstract-only results do not establish whole-paper absence. The cell
inspector's existing 4,000-code-point bound is retained. A longer saved passage
opens a labelled initial slice with its original range and omitted length;
attaching that slice never claims inspection of the omitted passage.

## Contracts and safeguards

- `BoundRetrieveEvidenceRequest.board_context` is optional. It identifies the
  board and revision, with either both paper/field identifiers or neither.
- The existing `EvidenceBoardService` resolves the owned definition and exact
  source preparation. It validates the current board/preparation before the
  original service ranks the restricted corpus. Unsupported or stale bindings
  fail explicitly; no current-source fallback is performed.
- Full preparation provenance stays in the original run fields. Canonical board
  context is additive under `parameters.board_passage_context`; legacy requests
  with no context retain their original idempotency fingerprints.
- Read-only `/boards/{id}/passage-search-context` and
  `/boards/{id}/passage-source-context` use the existing session authorization,
  lifecycle guard, source checks and bounded board reference contracts. The
  return path checks paper, source version, source/block hashes, exact Unicode
  quotation range, preparation manifest and board binding.
- A small optional `board_context` run-summary projection permits matching-run
  navigation without loading all passages into the workspace summary. A full
  selected run is checked again before display.
- Search drafts use `board-evidence:<board>:<revision>[:<paper>:<field>]` with
  canonical board/revision UUIDs and UTF-8 hex paper/field IDs. The existing server-validated CAS draft store and
  navigation barriers retain query, count and selected run separately from
  workspace-wide `evidence` and manual cell drafts. Questions/quotes/notes never
  enter URLs. Historical search drafts stay retained, while new retrieval and
  return into an editable cell require current bindings.

## Static demonstration

Only `showcase/portfolio` is prepared. The actual portfolio checkout is
unchanged. Comparison cells lead to **Saved example retrieval**, then the exact
existing excerpt and back to that cell. All nine excerpts come from the same
three attributed public sources; the saved result is curated display material,
not newly executed or ranked retrieval. Public-ID history state restores the
selection; no backend, browser storage, private workspace, API or model is used.

## Evaluation record

Executed on 24 October 2026. These are software checks, not human usefulness or
scientific support validation. Tests and browser use selected temporary
synthetic/public-example QA data, never the original research databases.

| Check | Actual result |
| --- | --- |
| Final focused backend/service/API tests | 131 passed, 0 skipped; 42.55 s; two inherited deprecation warnings |
| Independent existing MVP directory | 717 passed, 13 skipped; 30.20 s |
| Independent existing web API directory | 281 passed, 0 skipped; 251.94 s |
| Final complete frontend suite | 167 passed, 0 skipped; 3.314 s |
| TypeScript | PASS; also checked during the installed production build |
| Local-preview/deployment regression suite | 77 passed, 1 intentional opt-in Docker-image skip; 6.34 s |
| Exact final ZIP setup in a fresh application folder | PASS; 14.421 s; inherited hosted/model settings present; normal dependency caches available |
| Installed round-trip through the real Next.js bridge | PASS; 38 requests, 1.633 s; four prepared reports, three board reports, one cell report |
| Prior public QA records after final application replacement | PASS; 26 requests, 0.359 s; ten submitted revisions, pending drafts, 30-point saved map, sources, CSV/JSON and 13 access denials preserved |
| Public static projection | PASS; three CC BY sources, nine exact anchors, three explicit missing-information cells |
| Final isolated static export | PASS; 4.991 s; 21 public routes, 141 files, 528 local references, 29 fragments |
| Final local download bytes | PASS; ZIP, manifest and checksums each HTTP 200 and byte-identical |
| Reproducible archive | PASS; independent rebuild byte-identical; all 212 manifest entries verified |

The focused/backend and directory totals overlap and must not be summed. The
independent web API collection included 24 new passage-flow cases and the new
collection-context case before four additional count-validator cases landed;
the final focused suite covers those four too. The 13 MVP skips are missing
Streamlit/focused UI dependencies, not successful Streamlit parity checks.
Eight external static link targets were skipped without network checks.

The source tests cover wrong paper/field/board/run, hash/version/range/quotation
tampering, full-preparation manifest tampering, source-preparation changes,
unsupported/stale definitions, workspace deletion, abstract-only and empty
sources, explicit attachment and submission, old receipt replay, and CAS
conflicts. Mocked frontend tests also cover two-tab conflicts, blocked navigation,
older-run Back selection, validated run persistence and focus/position recovery.
No live literature-provider request, model or inference evaluation was run.

## Actual browser observations

The installed final production app ran at `http://localhost:3088/` with its API
on `127.0.0.1:8798`, using only the retained external public QA directory. The
browser walkthrough created a fresh three-paper/three-field board from the
approved Singapore, Japanese-women and Cheonggukjang sources.

- Board entry showed all three reports and a prefilled query without a run.
  Its edited query and count 10 remained separate from the cell search draft.
- The trial's exposure cell retained the unsent software-QA value while its
  field entry prefilled the exact subquestion. Explicit search for
  `Cheonggukjang tablets daily` requested ten, returned ten of 37 matched
  blocks, and indexed only that paper's 56 blocks.
- Opening result 1 returned to the existing source inspector with the exact
  retained quotation highlighted. The value remained unchanged, references
  stayed **0/5**, inspected ranges **0**, and judgment **Unassessed**.
- Refresh retained that exact source selection. Browser Back restored the
  edited query, count 10 and the same selected run. Explicit Back to cell
  focused the original trial/exposure cell. Keyboard Enter reopened its saved
  search; the table's observed horizontal position stayed **321.5 px** on return.
  Bounded history state also retains the departure scroll position; this is a
  UI navigation aid, not a cross-device bookmark or a pixel-stability promise
  after layout/viewport changes.
- A controlled stop and immediate relaunch of the final installation passed.
  Reopening the cell search without a run ID recovered the same stored run,
  edited query, count and ten passages. Returning its source again preserved
  the unsent cell value and zero declared references/inspection.
- Reopening the board-wide search while the cell run was the workspace's
  latest run showed the separate board query/count and **no selected run or
  passages**. No unrelated latest-run fallback occurred.

Actual static browser checks followed a diet cell through saved passage results,
exact context and return, used keyboard Return, refreshed a saved selection, and
used browser Back to refocus its original cell. The final export additionally
showed the reproductive-lifespan missing-information case, explicit limited
context warning, exact source offsets and the new .2 download link. The static
results are curated/precomputed, not a live ranking or research assessment.

The observed browser viewport was 1280 × 720. Mobile and an actual simultaneous
two-browser-tab conflict were not exercised; conflicts were tested in the
frontend and server CAS fixtures. The OS automatic browser opener was not
rerun; browser QA opened the ready application with `--no-browser`.

## Failures found and resolved

Independent source review found nested lifecycle locking in the first scoped
retrieval implementation and a missing full-preparation manifest check. Both
were fixed and regression tested. Long lexical blocks exceeded the existing
cell-reference bound; the final response exposes a labelled bounded range plus
the full original extent rather than changing ranking or silently claiming
inspection of the entire passage.

The first installed candidate exposed a real integration failure: the new GET
routes returned `404 bridge_error` because the Next.js allowlist did not yet
admit them. The fix adds only those read-only routes with exact bounded query
validation and denial tests. The final ZIP was rebuilt, installed in another
empty folder and passed the complete bridge/API/browser workflow. The earlier
candidate (SHA `a4bb246d…`) is retained privately as failed-stage evidence and
is not the current download.

Two initial combined-directory pytest invocations failed during collection
(duplicate module basenames, then sibling-import incompatibility in importlib
mode). Separate normal-mode directory runs passed without renaming tests or
changing application behavior. Early synthetic fixture/status assertions and
percent-encoded draft identities were corrected; canonical UTF-8 hex cell IDs
avoid route double-decoding ambiguity.

The prior preview's controller had exited while its two QA server children
still held locks. The launcher correctly refused to signal stale PIDs. Manual
read-only process/CWD/lock checks identified only those temporary public-QA
servers, then SIGTERM stopped them. The current final installation subsequently
passed normal authenticated stop/relaunch. Automatic orphan recovery remains
an existing documented limitation; no unsafe cleanup was added.

## Historical working-tree artifact and changed files

Historical archive: **lit-rev-engine-0.3.0-local-preview.2.zip**, **1,733,289 bytes**,
**212 files**, SHA-256:

```text
a493dec989fd2ea382de4039638552e215ee7ccd200fbf3abe91bc9378c90552
```

It is under `.mvp-web-state/releases/0.3.0-local-preview.2/`, with matching
`.manifest.json` and `.SHA256SUMS`; exact copies are prepared under
`showcase/portfolio/public/downloads/`. Version .1 remains historical and does
not contain this workflow. The package is still **Local preview — setup
required**, tested on macOS 26.6.2 arm64, Python 3.12.7, Node 24.19.0 and pnpm
10.20.0. Linux installation remains unverified; Windows is unsupported.

Workflow source/contract changes:

- `apps/web/components/workspace-app.tsx`, `compare.tsx`, `evidence.tsx`.
- `apps/web/lib/comparison-passage.ts` (new), `bridge.ts`, `openapi.json`,
  `generated-api.ts`.
- `src/mvp/contracts.py`, `board_contracts.py`, `evidence_board.py`, `service.py`.
- `src/web_api/app.py`, `board_routes.py`, `contracts.py`, `projections.py`.
- `apps/web/tests/comparison-passage.test.tsx` (new), `boundaries.test.ts`.
- `tests/web_api/test_board_passage_flow.py` (new),
  `test_collection_workflow_independent.py`.
- `tests/local_distribution/check_comparison_roundtrip.py` (new).

Packaging/documentation updates: `scripts/local_preview.py`,
`scripts/build_local_preview.py`, `tests/local_distribution/audit_source_archive.py`,
`docs/local_preview.md`, this report, and a historical .1 report pointer in
`docs/local_preview_evaluation.md`. The builder explicitly includes the reviewed
new frontend helper without staging untracked source directories wholesale.

Static overlay updates: `showcase/portfolio/src/components/LiteratureShowcase.tsx`,
its `.module.css`, `src/content/projects/literature-review-engine.mdx`,
`README.md`, and the three new .2 download assets. Public projection/source
files are unchanged. The original .1 artifacts remain retained.

The final preservation audit found all **195 protected files**, including the
original database hashes, unchanged; all **81 actual portfolio tracked files**,
feature HEAD/main references and the empty Git index were unchanged. Existing
README/.gitignore user changes, original research stores, operator-home patch,
inactive Render drafts and unrelated changes were preserved. No commit, push,
merge, deployment, release publication, paid call or private-data upload occurred.

## Reproduction commands and remaining limits

```sh
.venv-map/bin/python -m pytest tests/mvp -q
.venv-map/bin/python -m pytest tests/web_api -q
.venv-map/bin/python -m pytest tests/local_preview tests/deployment -q
# apps/web, with Node 24 selected on PATH:
node node_modules/typescript/bin/tsc --noEmit
node --import tsx --test tests/*.test.ts tests/*.test.tsx

python3.12 scripts/build_local_preview.py --output /absolute/new-empty-output
python3.12 tests/local_distribution/audit_source_archive.py \
  --archive /path/to/lit-rev-engine-0.3.0-local-preview.2.zip --report /private/tmp/archive-audit.json
# In the extracted archive, select installed runtimes as needed:
python3.12 scripts/local_preview.py setup --node "$NODE" --pnpm "$PNPM"
python3.12 scripts/local_preview.py launch --data-dir "$QA_DATA" \
  --web-port 3088 --api-port 8798 --no-browser
# From the engine checkout, use only a disposable public QA workspace:
python3.12 tests/local_distribution/check_comparison_roundtrip.py \
  --origin http://localhost:3088 --confirm-public-qa --report /private/tmp/roundtrip.json
.venv-map/bin/python showcase/portfolio/scripts/build_public_demo.py --check
# In the isolated website copy, after applying the review overlay:
NEXT_STATIC_EXPORT=true NEXT_TELEMETRY_DISABLED=1 SITE_URL=https://hnt119.github.io \
  node node_modules/next/dist/bin/next build
NEXT_STATIC_EXPORT=true SITE_URL=https://hnt119.github.io node scripts/check-export.mjs
```

Keep `$QA_DATA` outside the application and separate from original research.
Installed checks create synthetic/public QA records and are not read-only
against their target directory. Raw commands/logs, manifests, failed candidates,
browser screenshots and JSON reports remain in ignored
`.mvp-web-state/ui-checks/board-passage-roundtrip-2026-10-24/`.

Cookie/access recovery, optional separately installed models and manual orphan
cleanup retain the limitations in `docs/local_preview.md`. No cross-device
accounts, migration of the only data copy, paid inference, formal review
inclusion, retrieval usefulness benchmark or human validation was added.
