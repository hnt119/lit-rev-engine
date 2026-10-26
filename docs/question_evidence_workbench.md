# Question-to-evidence workbench — implementation checkpoint

Status: development, unreleased. Baseline: `265b291aaf0a2a60ac9aa89862dc531a78207874`, current reviewed main including source beta.4 `d52e5e35c80ef435abaec0c0a6f4ed236cba9356`. Work is isolated on `codex/question-evidence-workbench`. Releases, native packaging, Track B and research state are outside this change.

## Reuse and authority boundaries

| Existing authority | Additive change | Preserved boundary |
| --- | --- | --- |
| SearchPlanService, compiler v2, approved candidates and receipts | Readable intent grouping, revision-bound context and strategy export | Only an explicit plan revision changes executable intent; metadata never rewrites a query |
| Bounded provider diagnostics | Plain-language status panel | Three seeds/two calls; query membership differs from capped-preview recovery; failure differs from zero |
| Board definitions and submitted cells | Explicit typed normalization tied to a submitted cell and its sources | No inferred values from free text; the cell owns support, inspection and scientific history |
| BoardStore SQLite, workspace ownership and lifecycle guards | Append-only attribute/view records and bounded projections | No second database or eligibility ledger; views do not revise scientific definitions |
| Existing cell/source inspector and durable draft barriers | Filtered table/profile entry and stable return | Navigation never attaches evidence, sets support, submits or performs inference |
| Existing citation imports and approved JATS/abstract retention | External-strategy provenance and documented access gaps | A citation file is not a PDF attachment; local permission is not cloud-processing consent |

## Small implementation tickets

A1: expose required search concepts, later eligibility, preferences and extraction questions distinctly. Preserve unparsed expert queries byte for byte and approval/CAS/history behavior. Controlled vocabulary is unverified unless an authoritative entry is actually resolved; this checkpoint has no MeSH registry.

A2: project actual syntax/provider/count/sample/known-paper receipts into readable diagnostics and export a local strategy document. Offline, unrun and provider-failure states remain explicit. Export and navigation make no external requests. External execution records name the real platform and imported collection and must not claim a validated translation.

B1: add explicit multi-valued scientific dimensions tied to exact report, board/field/cell revisions and canonical evidence references. Unknown, not assessed, not found in inspected material, unreviewed and outdated remain separate. Recruitment geography does not establish identity. Report-level co-occurrence does not establish a same-cohort association.

B2: provide Overview, Methods and Needs review presets, named saved views, OR within facets/AND across facets, explicit unknown filtering, optional unreviewed values, sorting, grouping and visible fields. Preserve unique-report counts separately from group occurrences. Preserve active cells/drafts/focus and show a filtered-out active report explicitly. Full-board exports retain their current schema; current-view exports are separately labeled and include filter/source scope.

E1: prepare blank matched evaluation materials and an access audit. Three reports by five fields is a task design, not completed research. Participant judgments, timings, comparator access and scientific correctness stay NOT_RUN until genuinely observed.

## Checkpoint acceptance

- Manual planning and comparison work without an LLM or installed optional model.
- Existing immutable plan/board/source records and export schemas load unchanged.
- Wrong-workspace, wrong-paper, wrong-source, stale revision and conflicting-tab requests are rejected; no automatic rebinding.
- Multiple sample sites and unknown values survive reopening/export without false cohort links.
- View changes and strategy exports trigger no retrieval, preparation, indexing, generation or provider call.
- Excerpt → comment → reviewed save and comparison → passage → exact source → cell return retain drafts and explicit attachment.
- New software evidence is separate from old beta.4 validation. macOS and Windows execution statuses are reported individually; simulated Windows behavior is not an actual Windows run.
- No publication, release rebuild/replacement, main merge, native distribution, paid usage or private-data upload is part of this checkpoint.

See `question_evidence_access_audit.md` for access limitations and `question_evidence_evaluation/` for unfilled human/comparator tasks. Actual validation results are recorded separately after implementation.

## Persistence and compatibility rationale

New search-design notes use an additive, versioned table in the existing research SQLite store. They bind the exact saved plan revision; extraction questions and external-query provenance do not enter the compiler or alter approval receipts. The existing auxiliary-byte budget includes these rows. Workspace/plan ownership and deletion continue through the existing service and foreign-key boundaries.

Evidence dimensions, attribute revisions and saved-view revisions use three additive tables in the existing board sidecar. Its private-file, lifecycle lock, transaction, quota and workspace-deletion rules are reused. Old scientific definition/cell DTOs are unchanged: adding defaults to their hashed payloads would break historical integrity. Named-view revisions are immutable records with their own compare-and-swap version, independently of scientific board revisions. Drafts reuse validated scope-specific browser drafts and navigation barriers.

Source availability and review status are derived. Typed scientific values are explicit researcher normalization of an exact submitted cell or an explicitly unreviewed proposal, with immutable source anchors retained. A later cell, dimension or source change makes the projection outdated instead of changing its evidence silently. This layer does not decide review eligibility, independent verification, cohort identity or report-to-study linkage.

## Review materials

- [Task guide](question_evidence_user_guide.md)
- [Observed tests, browser checks, skips and remaining gates](question_evidence_validation.md)
- [Synthetic API/resource evidence](question_evidence_validation_software.json)

These are unreleased checkpoint materials. Existing release downloads are unchanged.
