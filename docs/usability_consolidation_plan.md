# Usability consolidation — implementation and acceptance

Baseline: `codex/mvp-v0-3` at `f2e1e4d2fcff5ceeb0b45b14a3ab1e4d8598de65`.
Scope: the supplied usability consolidation brief. Implementation and evaluation
ran locally; source release targets `codex/mvp-v0-3`. Existing research stores,
revisions, bindings, unrelated edits and the frozen retrieval engine are
preservation boundaries.

## Increment A — recoverable navigation and exact preparation handoff

- Implementation: root owns router outcomes, draft recovery and durable planner
  edits; Discovery owns persistent intake, result focus, selection headings and
  preparation handoffs; Backend owns bounded draft validation and ownership.
- Evaluation: reproduce the previous navigation failure in a frozen public-only
  browser harness; test draft save/conflict recovery, route switching and exact
  selected-set binding. Exercise search and collection paths without live calls.
- Acceptance: incomplete plans survive navigation/reload without compilation;
  failed saves visibly block navigation; selection counts agree; only the
  acknowledged clicked preparation opens board setup, with all selected papers.

## Increment B — a usable 30-paper comparison board

- Implementation: independently expand board capacity to 30 papers, six fields,
  180 cells. Keep AI, inspection, citation and synchronous preparation limits.
  Use one guided active cell editor and explicit acknowledged save/revision.
- Evaluation: populate and revise a 30 × 6 board, reopen and export it; check
  quotas and rollback. Walk through exact inspection, attachment, answer,
  judgment, submission and revision in the browser.
- Acceptance: all 180 cells are supported without mounting 180 editors or
  triggering per-cell retrieval. Unsupported/abstract-only information stays
  explicit. Manual drafts, suggestions and human support remain distinct.

## Increment C — adjustable passage search and accessible planning

- Implementation: UI requests any integer 5–30 (default five), preserving legacy
  API requests 1–4 and immutable request fingerprints/counts. Expose the existing
  optional typed local planner from an explicit Build search action; retain exact
  manual query input, compiler, approval and diagnostic boundaries.
- Evaluation: counts 5, 7, 10, 20, 30 and rejected 31; fewer matches; legacy runs;
  disabled/malformed/timeout/stale planner outputs; final desktop/narrow browser
  checks, fresh suites, typecheck and comparable production builds.
- Acceptance: no hidden model/provider calls, no paid fallback, no automatic
  human judgments, no production dependencies added. Real model, live PubMed
  and human usefulness evaluation are reported separately from software checks.

## Evidence and reporting

The evaluator captured original file/ref/store digests and consistent read-only
SQLite backups before edits. Public QA uses isolated temporary stores and ports.
Build comparison uses the same isolated path, Node and telemetry settings.
Final results, actual commands, failures/skips, browser observations, changed
files, size deltas and limitations belong in the companion evaluation report.

Implementation references: [React state preservation](https://react.dev/learn/preserving-and-resetting-state),
[CSS sticky positioning](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/position),
[accessible status messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html),
and [PubMed query help](https://pubmed.ncbi.nlm.nih.gov/help/).
