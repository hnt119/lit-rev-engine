# Manual source-linked comparison board

> Historical manual-board checkpoint: the labels, startup configuration and 10-report / 60-cell limits below describe that checkpoint. The current feature branch supports up to 30 reports / 180 cells and uses **Select evidence → Comment & judge → Review & save**. Use the [version-matched user manual](user_manual.md#select-an-excerpt-comment-and-save) for current steps and [Evidence Gap Navigator](evidence_gap_navigator.md) for follow-up investigation. All original checkpoint sections and anchors are retained.

This checkpoint adds **Compare** to the existing local Next.js/FastAPI workspace. It reuses retained searches and preparations; it does not search again, run a model, refit maps or change existing assessments. A board is a report-by-field table, not a statement that the reports are independent studies.

## Start locally

Use the existing Python 3.12 / Node 20.9+ installation and web environment described in [the web guide](mvp_v0_2.md). For a fresh environment:

```sh
python3 -m venv .venv-web
.venv-web/bin/python -m pip install -r requirements-web-dev.txt
cd apps/web
pnpm install --frozen-lockfile --ignore-scripts
cd ../..
.venv-web/bin/python scripts/run_web.py --data-dir .mvp-web-state
```

Open `http://127.0.0.1:3000/` in the same browser that owns the workspace. Stop with Ctrl+C. For production-mode local operation, build in `apps/web` with `NEXT_TELEMETRY_DISABLED=1 pnpm build`, then add `--production` to the launcher. Reuse the existing data directory; do not replace or migrate the only research copy. The launcher does not automatically load `.env`. Reopening an existing live-mode workspace still requires its existing `NCBI_EMAIL` process configuration because the shared service bootstrap validates it; see [the v0.3 startup instructions](mvp_v0_3.md). Board operations make no provider requests and require no embedding libraries or inference credentials.

## Complete a manual comparison

1. Open a retained research workspace. In **Discover & explore**, prepare the selected papers if a retained preparation is not already available. Live preparation may contact its existing providers; board operations use only the resulting saved sources.
2. Open **Compare**, then **Create comparison board**. Select three prepared reports and keep or edit the three initial fields: Population, Study design and Exposure or intervention. Each field has its own editable retrieval subquestion. Save the definition.
3. Select one of the nine cells. **Retrieve candidates for this cell** ranks only this report's prepared source using that field's subquestion. Empty results establish no absence finding.
4. Inspect a candidate in its **exact retained source**, or browse the canonical source directly. Read omitted-range labels and paginate as needed. Choose half-open Unicode code-point offsets; explicitly mark the range inspected. Add the chosen range as a reference separately.
5. Enter a manual value and choose a human support judgment and inspected-scope result. Give a reason. Record missing information explicitly where appropriate. **Submit cell** submits the acknowledged saved draft; opening context, retrieving candidates and autosaving drafts never submit a judgment.
6. Use **Revise saved cell** to begin an explicit revision. Submit it to supersede the prior immutable cell. Load cell history to inspect original quotations and reasons.
7. Reopen the workspace and board in the same browser. Saved drafts, submitted heads and history persist. Download the board CSV and audit JSON. Unsubmitted drafts are excluded from exports.

**Abstract only** remains visible beside the report and in the cell editor. “Not found in inspected material” refers only to the declared ranges, never the unretained full paper or the wider literature. If no source text is available, retain a null value, explain the unavailable material and use **Not assessed** for scope; no inspected range is invented.

## State, integrity and revision rules

These dimensions remain separate:

| Dimension | Representation |
| --- | --- |
| Source availability | Original preparation status and `full_text`, `abstract` or `none` |
| Candidate relevance | Lexical ranking, scores, indexed/matched/returned counts and omissions; no support claim |
| Declared inspection | Human-selected canonical source ranges; opening the inspector does not declare inspection |
| Mechanical reference integrity | Exact server-reconstructed quotation and checked source/version/block hashes |
| Human support | `unassessed`, `human_supported`, `partial` or `unsupported` |
| Inspected scope | `not_assessed`, `value_found` or `not_found_in_inspected_material` |
| Freshness | Current definition/preparation, or historical dependencies shown read-only |

Human-supported requires a nonblank value, a reason, checked references, value-found scope and inspected ranges containing every cited range. Mechanical quotation matching does not establish entailment. All submitted null values require a reason and a missing-information statement; blank text is not a substitute for null. Not-found scope additionally requires actual declared inspected material. An unassessed manual value can remain explicitly unassessed.

Every submission is **single-human, self-declared, not independently verified**. Software walkthrough entries are not scientific validation or a second reviewer's judgment.

A stable board has immutable definition revisions. Each revision binds the original saved search and its digest, question and digest, preparation/source revision, source manifest, ordered report IDs, field revision IDs and lexical profile. Bibliography comes from that original search even if a later search returns the same PMID. Changing the question, fields or prepared sources creates an explicit definition revision with empty, unassessed new cells; old heads are not inherited.

Typed cell drafts have their own version and expected cell head. PUT checks the definition, draft version and current submitted head. Submission checks the acknowledged draft version and explicit supersession atomically, then consumes that draft. A later revision starts explicitly from the latest head. Conflicts and rejected submissions preserve the saved draft; the interface retains conflicting edits for comparison and explicit rebasing.

## Additive service and storage

`EvidenceBoardService(registry, service_for, BoardStore(path))` is the application boundary. Public operations receive the workspace mode and authorized handle before board-specific arguments:

```text
create / listing / view / revise
candidates
get_draft / put_draft / submit / history
blocks / reference_context
export
```

`src/web_api/board_routes.py` exposes these through the existing `/api/v1/workspaces/{w}/boards` session boundary. Host/Origin checks, CSRF protection, authorization and request-size protections remain shared with the existing API. Contracts are in `src/mvp/board_contracts.py`; OpenAPI generates the frontend types.

The private additive sidecar is `<data-dir>/evidence-boards.sqlite3`. It stores definition revisions, cell revisions and heads, typed drafts, candidate runs, request idempotency and deletion tombstones. It does not replace the research or map database. The file is created with mode 0600 in the private data directory. Mutation lock order is lifecycle guard → existing serialized research snapshot → short board transaction. Workspace deletion also clears board records and retains a tombstone so delayed operations cannot recreate them.

Existing `WorkspaceSnapshot`, source preparation, passage retrieval profiles, Qwen profiles, map artifacts, assessments and historical citations are preserved. The ranker is the existing `LexicalRetrieval.search`, scoped to one report and one field. No generation, synthesis, new database platform, MCP or deployment is added.

## Bounds and projections

| Resource | Limit |
| --- | ---: |
| Reports per definition | 10 |
| Fields per definition | 6 |
| Cells per definition | 60 |
| Boards per workspace | 10 |
| Definition revisions per board | 20 |
| Submitted revisions per cell/definition | 50 |
| References per cell | 5 |
| Declared inspected ranges per cell | 30 |
| Sidecar payload budget per workspace | 32 MiB |
| Candidate matches per operation | 3 |
| Candidate quote per match | 1,200 code points |
| Inspector range per block | 4,000 code points |
| Inspector blocks per response | 3 |

Quota failures roll back the attempted mutation and preserve existing data. Candidate responses include omitted-character and omitted-matched-block counts. Canonical inspector responses retain original offsets and total lengths, with previous/next ranges for oversized blocks. Normal board projections include compact bibliography and cell heads with reference metadata, without repeating source quotations. Full quotations are available through explicit context, immutable history and exports. Reads, filters and navigation do not trigger retrieval or inference.

## Separate board exports and future proposals

CSV uses `mvp.board-table.v1`; audit JSON uses `mvp.board-audit.v1`. Exports retain original bibliography, question/field/source bindings, nulls, separate state dimensions, exact anchors, producer and supersession ancestry. CSV contains submitted heads for the selected definition and applies existing formula-safe encoding. Canonical values remain unchanged in JSON. Audit JSON always includes the selected definition's immutable cell history and candidate audit; the history option additionally includes earlier board definitions. Unsubmitted drafts are excluded. Existing evidence and `mvp.audit-bundle.v1` export schemas are unchanged. Source-linked exports stay local unless separately approved for sharing.

Submitted cells retain `producer: manual`. The subsequent [optional cell-proposal checkpoint](cell_proposals.md) adds separate, version-bound AI suggestions and adoption/dismissal records to this board. Generation remains disabled by default. Suggestions do not replace manual submissions, declare inspection or certify support; adoption and explicit human submission remain separate. The original manual-checkpoint [evaluation record](manual_board_evaluation.md) remains historical.

## Verification boundaries

Domain and API tests check source ownership/hash/range validation, Unicode offsets, candidate/inspection/judgment separation, draft and submission CAS, ancestry, bounds, idempotency, CSV safety, original bibliography and deletion races. Browser checks and their exact executed results belong in the checkpoint evaluation record. Live provider execution and real embedding execution remain separate recorded discovery evidence; board checks do not repeat or upgrade those claims. Software passing these checks does not establish human usefulness, scientific completeness or superiority over another review tool.
