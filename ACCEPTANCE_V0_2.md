# MVP v0.2 — release acceptance

**Baseline:** `codex/mvp-v0-1`, observed at `8df5993c86893d47620a101a2319c564cff2d494`.  
**Status of this checklist:** proposed checks, not completed results.

Record the actual commit/environment for every check. Report passes, failures and skips; never replace execution with the branch's historical counts. Checkpoint v0.2a may be delivered before v0.2b, but the whole release is not complete until both are accounted for.

## A. Baseline and compatibility

- Confirm the working branch contains the MVP baseline, not only old main. Preserve unrelated local changes and private `.env`/research data.
- Run the focused `tests/mvp` suite in its supported environment. Report Streamlit tests skipped when the dependency is absent; do not count them as UI coverage.
- Run relevant legacy tests and the existing frozen-artifact rehash checks. Do not edit manifests or frozen expected values to make the release pass.
- Existing Streamlit and headless smoke remain usable with their original focused dependency group.
- New web/model dependencies remain optional. Importing core services must not import Next.js, Streamlit, model weights, or trigger network requests.
- Add a failing-then-passing regression for the recorded question/query draft navigation issue. If the branch already fixed it, preserve and cite the current regression instead of reverting it.

## B. Persistence, isolation and drafts

- A newly created web workspace is reopened in the same browser after reload, tab closure/reopen, and API/frontend process restart while the persistent session is valid.
- Resume uses the same workspace ID and saved records, not a re-created workspace that happens to look identical.
- Session A cannot list/read/mutate Session B's workspaces by guessing identifiers. Read-only endpoints, drafts, maps, jobs, source context and exports obey the same rule.
- Capabilities are absent from URLs, generic responses, browser storage, logs, exported JSON/CSV, generated OpenAPI examples and public assets.
- Expired/cleared-cookie behavior is explicit. No backdoor recovers a lost workspace by UUID or relabels local sessions as named human identities.
- Question, query, selection and judgment drafts survive route changes and a reload after successful draft persistence. UI clearly distinguishes unsaved, saving, saved and failed state.
- Failed draft/assessment saves and 409 conflicts retain the user's edits; stale autosave cannot overwrite a newer revision.
- Saving a draft does not create an assessment. Inspecting source, clicking a point, or changing a filter does not save, prepare or search.
- Clear/delete removes authorized workspace-owned auxiliary state and access bindings. Late map results cannot recreate it. Do not claim secure disk erasure.

## C. Discovery and evidence parity

- Preserve exact query, question, sort, supported dates, provider translation, timestamps, total/fetched/distinct counts, ordered identifiers and warnings.
- Default 30 / maximum 50 discovery records; maximum 10 prepared papers and 5 returned passages. Invalid bounds fail before network work.
- A preview always retains its exploratory schema/label, including when reported matches happen to fit the cap.
- Saved-example mode says saved/offline and does not call PubMed. Refresh is an explicit new operation; ordinary React renders/reloads do not repeat it.
- Repeat submission with the same request ID and same body reuses committed results; changed-body reuse returns conflict. Persist pending request IDs across ambiguous response loss.
- Source selection is scoped to the specified saved search. Hover or a changed selection draft does not silently change the active preparation.
- Sources preserve status, full-text/abstract distinction, identity/permission failures, source hashes, canonical blocks and parser provenance.
- Retrieval requests cannot race to a different preparation than the one the user saw. Enforce expected binding inside the service's serialized operation.
- Empty/irrelevant questions do not get unrelated fallback passages. Method/profile/parameters remain the existing lexical baseline.
- Unicode exact-source highlighting works with emoji, astral characters, combining characters and escaped markup; code-point offsets are not used as UTF-16 offsets without conversion.
- Null/unreviewed states stay neutral. An assessment has exactly the current service's support/reason requirements and explicit revision chain.
- A stale run cannot be assessed as current. Historical read-only context verifies its original preparation and bibliography; updated metadata for the same PMID does not rewrite it.
- CSV escaping and original JSON text/history remain intact. Existing audit schema is not silently expanded with session secrets or map state.

## D. Semantic mapping

- Map input is one exact search snapshot and metadata digest; the same paper ID with changed metadata does not reuse an obsolete embedding unconditionally.
- Cache keys bind model/tokenizer revision, representation/length policy, dimension and normalization as well as input text.
- No hidden model download or paid inference. Missing setup yields a clear disabled map and a fully working evidence path.
- Token-window aggregation covers the full declared representation; long abstracts are not silently clipped. Title-only input is labeled.
- Test zero, one, two, small, and at-least-20 vector sets; identical/rank-deficient vectors; NaN/infinity; wrong dimension; zero norm; and excluded-paper counts.
- The single real saved example does not show fake neighbors. Synthetic fixture points are unmistakably software-test data.
- Saved coordinates, ordering and point identity survive reload/restart. Filtering, table sort, source inspection, assessment saves and navigation do not refit.
- Explicit rebuild creates a distinct map artifact. Old maps remain inspectable without replacing current evidence or bibliography.
- Neighbor order is based on original-space cosine similarity, with stable ties and no external discovery call.
- Map/table selection stays synchronized by stable paper IDs. The same operation is possible from a keyboard-accessible list.
- Labels distinguish provider matches, displayed records, embedded papers, excluded papers and filtered-visible points.
- No evidence-strength scoring, automatic clusters, topic labels or “research gaps” are inferred from the picture.
- Real map smoke is reported separately from injected-vector tests. Do not claim actual embedding integration was exercised when only fake vectors ran.

## E. Job and storage boundaries

- Map submission is persisted and returns a job reference; duplicate requests do not create duplicate committed maps.
- A worker crash produces a recoverable/interrupted state, not permanent apparent progress or false success.
- Attempt ownership prevents a late worker from finalizing over a newer attempt. Validate the full map before atomic publication.
- Map calculation holds no long SQLite write transaction or workspace mutation lock. Reading/assessing existing evidence stays possible.
- Cancellation is explicit and cooperative. Artifact publication after deletion or unauthorized reassignment is rejected.
- New artifacts do not multiply vector/XML payloads throughout the existing serialized snapshot and idempotency history. Test auxiliary-state bounds and rollback on limits.
- Added tables/migrations preserve original snapshots and IDs. Back up and restore a copy, compare source/assessment hashes, and test the old reader where compatibility is promised.
- Only one process performs provider calls under the current process-wide limiter. Document the prohibition on concurrently treating several live app processes as sharing that gate.

## F. Browser and presentation

- Use a real browser check, not only JSX snapshots or API tests, for create/search/select/prepare/inspect/save/revise/export/reopen.
- Confirm the existing paper/ink/olive tokens, restrained layout, visible focus, keyboard actions and reduced-motion behavior.
- Desktop: matching passage/judgment rows remain aligned, with source context clearly reachable. Mobile: passage → its judgment → next pair; no main horizontal overflow.
- Source navigation preserves unsaved notes and does not create provider calls. Intentional screen transitions do not preserve a misleading stale fragment/scroll position.
- Test loading, no matches, no full text, map unavailable, provider timeout, permission failure, stale state, and failed save—not only successful sample data.
- No untrusted paper/model text becomes executable HTML or an arbitrary fetch URL. Keep fixed provider endpoints and safe outbound links.

## G. Demonstrations and result labels

Three demonstrations have different evidential meaning:

1. **Offline software run:** mocked providers + deterministic vectors + existing licensed example, in a new temporary workspace. Demonstrates contracts and UI, not live availability or scientific usefulness.
2. **Approved live smoke:** exact approved PubMed query, configured contact, bounded requests, genuine provider receipt and source outcomes. Zero results/permission failures are legitimate outcomes. The architecture review did not run this.
3. **Optional model smoke:** explicitly configured local weights, real saved metadata, recorded profile and generated coordinates. Demonstrates integration, not a validated ranking benchmark.

Judgments made only to exercise tests must be marked synthetic test judgments. No check establishes independent scientific verification or an exhaustive systematic review.

Final report must include:

| Area | Status | Exact evidence |
|---|---|---|
| v0.2a workspace parity | IMPLEMENTED / PARTIAL / NOT_IMPLEMENTED | Browser flow and test commands |
| Reopening and drafts | TESTED / FAILED / NOT_RUN | Restart/conflict cases |
| v0.2b map implementation | IMPLEMENTED / PARTIAL / NOT_IMPLEMENTED | Artifact and behavior checks |
| Real embedding smoke | TESTED / FAILED / NOT_RUN | Model revision, inputs, outputs |
| Live PubMed end-to-end | TESTED / FAILED / NOT_RUN | Approved query and actual outcome |
| Legacy/frozen preservation | TESTED / FAILED / NOT_RUN | Current execution/checksum results |
| Hosted deployment | OUT_OF_SCOPE | No public deployment in this assignment |

Provide implemented startup/shutdown commands, environment prerequisites, durable data location, limitations and changed files. Never publish a guessed command as though it already exists.
