# Protocol review pilot — integration boundary

Baseline: `cb98e3ef843982ebe0cfb65631d8f923a1a4007b`.
Track B lives on `codex/protocol-review-pilot`. The frozen local preview,
its checksums, packaging defaults, optional models and deferred hosted work
are preserved. Track A is blocked on the owner's license decision; this work
does not choose terms, rebuild the release or publish anything.

## Inspected authority and unsupported behavior

`ReviewStore` owns citation identity, original occurrences, screening and
retrieval events, report/study associations, immutable source bytes/blocks,
counts and one-snapshot audit exports. The web workspace remains responsible
for session ownership and comparison state. Collections and boards do not
establish formal review inclusion.

Before this patch, protocols are create-only strings; ordinary file imports
retain parsed occurrences but not the original export bytes; screening has no
CAS token; reviewer labels are unauthenticated. Title/abstract reopening after
retrieval and retrieved-status downgrading are intentionally unsupported.
Full-text retrieval is a declaration, not proof a document was read. Study
totals remain null without complete explicit associations.

The existing complete PubMed capture verifier supports exact membership up to
10,000 records, without segmentation/resume. Exploratory previews and generic
imports cannot assert that a query capture is complete. Existing retained-source
handoff supports permitted JATS and explicitly typed abstract-only sources;
unsupported TXT/PDF handoff must fail explicitly, without coercion.

## Small implementation tickets and interfaces

1. **Ledger / Retrieval:** additive opt-in `ReviewStore` pilot support for
   append-only protocol revisions, intake-byte retention and decision/status
   bindings. Keep original APIs/export schemas backward compatible. Use
   expected protocol/event heads and request IDs for retries/conflicts. No
   second screening table or automatic decisions. Exact original inputs and
   source attribution must survive reopening and audit export.
2. **Adapter / Implementation:** one thin owned-workspace pilot adapter and
   FastAPI routes. Initialize only a new isolated review project. Resolve all
   report/source IDs on the server. Explicitly publish a selected working
   subset through the existing immutable collection/preparation and board
   services. Record protocol/event/document/version/hash → comparison bindings.
   Source attachment, retrieval status, screening and handoff are separate
   actions. Abstract-only coverage never becomes retrieved full text.
3. **Reviewer interface / Coordinator:** a small page within the current web
   application for protocol versions/unresolved choices, intake, paged library,
   reasons/history, source attachment, explicit comparison handoff and audit
   export. Reuse session/origin protection and navigation draft barriers. Show
   self-declared reviewer and one-reviewer limits. Keep original exploration UI.
4. **Evaluation:** independently audit one disclosed 30-record sample, counts,
   retry/concurrent edits, protocol/source binding, unauthorized access,
   reopening and exports. Actual browser checks are recorded separately from
   API tests and synthetic decisions. No real human screening is inferred.

No change to ranking algorithms, frozen retrieval profiles, map artifacts,
assessment rules, historical source bindings or board export schemas.
Library intake is paged independently of the existing 30-source board cap.
Handoff selection never sets eligibility, support or independent verification.

## Protocol and sample limitations

Known owner preferences: systematic review; Asian-origin women, with Southeast
Asia preferred; gut microbiome in relation to reproductive longevity, healthy
aging, gynecological disease and diet/exposome; sole reviewer proposed for the
pilot. Age limits, mixed-population rules, study designs, required outcomes,
search coverage/dates/languages, appraisal and disagreement procedure remain
unresolved. No real review is declared ready from those preferences alone.

Software usability sample: all 30 approved public example records in retained
manifest order. The source collection reports Europe PMC total 194, metadata
100 and rights/identity-filtered retained 30. Importing all 30 means complete
intake of that supplied set, **not complete query capture**. Any duplicate
reimport is disclosed separately. These sources were not chosen by model score.
An abstract-only case is deliberately restricted coverage: full text exists in
the public set. Software-QA screening actions are scripted and have no clinical
or real eligibility meaning. A separate synthetic capture verifies the genuine
complete-capture path without claiming a new live PubMed execution.

## Acceptance and next decision

Protocol versions and unresolved choices survive reopening. Every occurrence
reconciles into canonical records and duplicate counts. Exclusions retain
reasons and every original decision; stale writes fail. Selected reports bind
to exact retained sources before opening the existing comparison workflow.
No search, screening, attachment or inference runs on navigation alone.
Pending/conflicting/abstract-only states remain visible. Counts are reproduced
independently; reports are never equated with independent studies. Audit exports
retain protocol/intake/source/handoff history and replay after original inputs
move. Original user data, release assets and actual portfolio stay unchanged.

Evaluate workflow costs and observed problems in a separate report. This
software sample is neither a completed systematic review nor an independent
retrieval-accuracy benchmark. A real sole-reviewer session remains a separate
unperformed human validation until the reviewer actually does it.
