# Next milestone: one protocol-defined human review pilot

Status: **saved and planned**. The accepted foundation release is `69e7a6b`; its software and bounded retrieval evidence are preserved. This next milestone requires a review team's actual topic and protocol. No real search, screening or model inference has started, and no topic or medical conclusion is assumed.

## Objective and starting inputs

Complete one manageable real workflow pilot from saved searches/imports to auditable current evidence and reconciled exports. Approximately 20–50 records and several full texts are a proposed initial usability sample, not a complete systematic search or publishable review by themselves.

The review team supplies the review type (systematic/scoping), question, population/topic boundaries, inclusion/exclusion rules, databases, exact search strategies, dates/limits, outcome/extraction fields, appraisal approach, reviewer roles and disagreement rules. Save the protocol reference/version before selecting records. Keep systematic and scoping objectives distinct; the current project stores supplied metadata but does not validate methodological choices.

Use a new durable database/project, separate from software examples and frozen benchmark data. The [starter guide](getting-started.md) establishes the current commands; [architecture](architecture.md) explains which state is authoritative.

## Stable interfaces

Imports preserve original records, each occurrence, search metadata and capture receipts. Screening and full-text status are declared reviewer events with reasons. Study links are explicit complete association sets. Attached source versions retain bytes, hashes and typed locators. Evidence proposals retain exact quotations and context; verification references the current immutable revision. Exports include current eligible/verified evidence alongside complete audit history and reconciled counts.

Model-generated relevance and text are assistance only. The [cloud strategy](model-strategy.md) is optional future integration. The pilot should first expose missing workflow support and demonstrated errors in the existing CLI, rather than depend on an unevaluated model choice.

## Small role-specific tickets

| Owner / ticket | Deliverable | Acceptance criteria |
| --- | --- | --- |
| Coordinator P0 | Pilot protocol/reference, scope and acceptance receipt | Actual team-supplied question, eligibility, search/source choices, fields, review roles and disagreement rules recorded before pilot decisions. Unknowns remain explicit. |
| Retrieval R25-pilot | Search/import/source provenance for the chosen sample | Exact executed strategies/dates/limits, original exports/captures and membership; source identities/version/permissions; coverage gaps and sampling rules disclosed. No benchmark-driven query selection. |
| Implementation I10-pilot | Guided pilot sequence and only demonstrated fixes | Existing CLI completes import/history/dedup/screening/linkage/source/evidence/export steps in the new project. Any fix has a narrow interface and regression evidence. No unrelated default or frozen-artifact change. |
| Evaluation E15-pilot | Independent artifact/count/source audit | Independently calculate occurrence/record/report/study totals; inspect reasons, conflicts and quoted evidence; reproduce exports from the retained ledger after original input deletion. Explain every discrepancy. |
| Coordinator P1 | Evidence review and next decision | Review observed failures/usability costs, accept or reject the pilot against its recorded criteria, then choose the single highest-value next ticket. |

Retrieval R25-pilot is the future protocol-data task; the separate pre-pilot R25 research supplied the cloud-model shortlist. Roles do not substitute for independent human reviewers or topic expertise.

## Acceptance evidence

Every imported occurrence is accounted for through canonical records and duplicate counts. Search history retains known strategy/date/filter details and exact bytes/checksums; completeness limits are visible. Screening, full-text outcomes and exclusions reconcile with explicit pending/unresolved partitions. Every included report has a resolved study association before a final study total is accepted.

Key extracted values and appraisal judgments have original-source quotations, context and independent review under the team's protocol. Preserve each person's original extraction and decisions when reconciling disagreements. A source mismatch, replacement or unresolved association suppresses current verified evidence while preserving history. Reconciled arithmetic alone cannot establish completed or valid extraction.

Exports from unchanged retained state reproduce after original input files are removed. No input deletion is performed until the pilot has demonstrated that all needed bytes are preserved and backed up. Differences between fresh-ledger UUIDs and same-ledger determinism remain explicit.

For intervention systematic reviews, Cochrane recommends piloting collection forms, linking multiple reports of a study, and independently extracting key outcome data with at least two people. The pilot must reflect its own review type and team procedure. [Cochrane data-collection guidance](https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-05).

The final report lists missing support, disagreements, source discrepancies, incomplete states and time spent on workarounds. The next engineering priority follows that evidence. It may be a reviewer interface, stronger extraction forms, database coverage, study-link conflict handling or a bounded cloud-retrieval experiment; none is preselected as a demonstrated need.
