# Usability consolidation

Implementation baseline: `codex/mvp-v0-3` at
`f2e1e4d2fcff5ceeb0b45b14a3ab1e4d8598de65` (23 October 2026).
The [implementation plan](usability_consolidation_plan.md) follows the supplied
usability brief. Source release targets `codex/mvp-v0-3`; runtime state and QA
artifacts remain local. Merging, deployment, paid inference and publication of
private research data are outside this checkpoint.

## Using the consolidated workflow

1. **Add papers.** Search papers, Import papers and Browse collections stay
   available before and after discovery. The intake pane has its own URL state;
   switching it preserves the mounted result list, local filter, map and focused
   paper. Planner edits and identifier input save as bounded local server drafts.
2. **Select & prepare.** The list, map and inspector share one selection draft.
   Counts include selected papers outside the current filter. Select up to 30 and
   choose **Prepare & compare (N)**. Current exact preparations offer
   **Continue to comparison (N)** without another source fetch.
3. **Create the board.** Setup uses the acknowledged clicked preparation and all
   its selected papers, including abstract-only/unavailable outcomes. Edit the
   question and 1–6 fields, then explicitly create the board. A matching saved
   board is offered where available. New boards disclose a pinned B1 exact-span
   profile when available; existing definitions retain their original profile.
4. **Complete a cell.** Rows are papers; columns are comparison questions. Open
   one cell, **Find relevant passages**, then **Read in source**. The exact span is
   highlighted. **I have read this excerpt — attach as evidence** adds its range
   and reference together. It does not choose a human support judgment.
5. **Save deliberately.** Write an answer or explain missing information, choose
   your own judgment and scope, then **Save cell to table**. Autosaved drafts are
   separate from submitted cells and exports. The acknowledgment says **Saved to
   comparison**; **Edit saved cell** starts an explicit revision. Next incomplete
   cell means a cell without a submitted current value; progress separately
   reports saved cells and human-supported cells.
6. **Export.** Board CSV and audit JSON use the existing schemas, exact source
   anchors and immutable history. Exporting does not independently verify a
   judgment. History/export and optional passage search remain accessible.

A 30 × 6 board renders 180 compact cell buttons and one active editor. Candidates,
source context, proposals and history load on explicit demand. On wide screens
that editor sits beside the table; narrower screens use an in-flow pane. The
paper/ink/olive theme and portable tokens remain unchanged.

## Draft and navigation recovery

Incomplete planner intent can be saved without compiling, approving, diagnosing
or executing a query. A failed save returns a blocked navigation outcome and
keeps edits. Retry retains edits but refuses to overwrite a newer draft from
another tab. Stay leaves the current view alone. Explicitly confirmed restore
loads the saved draft before continuing. Historical plan inspection shows its
immutable revision, while unfinished current edits remain separately retained.

Identifier input stores only its format and text (20,000-character bound), never
file bytes. Unparsed files, unfinished import review/metadata and collection
combination edits block app navigation until acknowledged or explicitly reset.
Dirty/pending inputs also request the browser's native leave confirmation on
reload/close. Confirming leave cannot preserve a browser File object: select the
file again when returning. This is a guard, not server persistence of raw files
or unfinished review forms. Existing parsed import previews remain retained.

Draft quotas remain 64 KiB per record and 2 MiB per workspace. Very long passage
notes or Unicode identifier text can exceed them: edits stay local and navigation
blocks until shortened, saved through the appropriate operation, or explicitly
restored/discarded. Native browser confirmations depend on browser support and
user interaction; they cannot perform an asynchronous save during unload.

## Optional search planning and passage search

**Research question → Build search → Review proposed search → Check matches →
Search papers** uses the existing typed local planner. Build search explicitly
saves a needed question revision, then makes one bounded planning request. The
model proposes; the researcher adopts/edits, reviews terms and approves the exact
compiled query. Deferred restrictions still need separate acknowledgment. MeSH
terminology rules remain enforced. Boolean trees, spans and receipts remain in
Advanced. **Paste my own query** preserves expert strategy bytes and follows
separate approval/diagnostic/execution steps. Disabled planning shows its actual
reason and setup guidance; there is no paid/remote fallback or hidden retry.

Passage search requests any integer **5–30**, default five. The API still accepts
legacy values 1–4. New immutable runs record requested `parameters.top_k` and
actual `parameters.returned_count`. Fewer matches return fewer passages; old
runs retain their original shape and settings. Changing the control affects the
next run. It does not change ranking, board candidate limits or proposal packets.

Independent limits remain: 30 prepared sources; synchronous preparation 10;
30 board papers × 6 fields = 180 cells; five cell references; 30 inspected ranges;
3 candidate passages per board field; AI proposals 3 papers / 9 cells / 3 calls.
The board workspace quota remains 32 MiB and idempotency retains its existing
request quota. Maximum-length values across every possible revision are not
promised to fit simultaneously.

## Implementation boundaries

The existing Python services, SQLite stores, source versions, lexical retrieval,
map coordinates, assessments, exports and proposal adapters remain the engine.
This change adds bounded UI draft scopes and small summary fields; it introduces
no generation adapter, platform, production dependency or new research engine.
Board summary fields have defaults for old retained receipts. Existing definition,
cell and evidence schema versions and historical hashes are preserved. New run
parameters copy the ranker's settings rather than mutating shared profile state.

See [evaluation and delivery evidence](usability_consolidation_evaluation.md) for
actual commands, outcomes, browser observations, file scope and limitations.
