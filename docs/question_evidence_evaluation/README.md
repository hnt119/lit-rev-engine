# Blank evaluation kit — question-to-evidence workbench

**Status: design/templates only.** No participant recruitment, consent, observations, timings, gold answers, live query checks, model calls or competitor access has occurred for this kit. Empty cells are deliberately empty, not zero or a successful result. Existing software/release checks do not fill them. The separate [software resource summary](../question_evidence_validation_software.json) records a synthetic API case and its exact input hashes; its sub-second mechanical transitions are not participant review times or scientific findings.

This kit evaluates an explainable search and a source-checked three-report/five-field table. It does not evaluate complete systematic-review recall, screening eligibility, market superiority or general model superiority. Proposed initial group: 3–5 unrelated biomedical postgraduate researchers or research assistants. Any existing reviewer may be one participant; prior unfavorable feedback remains separate and must not be overwritten.

Before any session, complete and approve [protocol.md](protocol.md), [tasks.md](tasks.md), [comparators.md](comparators.md), and [seed_lock.md](seed_lock.md). Use [participant.md](participant.md) and [observer.md](observer.md) without coaching the workflow. Record actual data privately using the header-only CSVs in `templates/`. Keep names, consent, recordings, cookies, workspaces, raw exports, institution details and unpublished research outside Git and release assets. Use participant codes in any sanitized report; do not promise anonymity beyond what is actually implemented.

[analysis.md](analysis.md) defines measures and uncertainty. [acceptance.md](acceptance.md) maps proposed software tickets onto existing offline and source-distribution harnesses. No evaluation should start merely because the software passes.

## Safe document selection plan

For software development, reuse unchanged licensed sources and hash metadata from `examples/mvp/offline_microbiome_30_v1/` plus clearly synthetic boundary fixtures. A candidate real participant set is PMID 42051515 / PMC13110953, PMID 42196995 / PMC13209271 and PMID 38684759 / PMC11058859. These are **candidates, not selected or independently adjudicated gold**. All have retained CC BY 4.0 XML and attribution in the existing manifest. Verify study/report type, actual multiple-cohort or multiple-site content and field coverage by reading before locking a set; title or metadata keywords are insufficient.

The final set must contain an actual multi-cohort or multi-site report and at least one honest insufficient-information task. If one report is deliberately supplied as abstract-only, label that as the task's provided source scope, give exactly the same scope to every comparator, and do not claim its full text is unavailable. If these candidates do not meet the task, leave selection pending rather than inventing findings or downloading replacements without authorization.

A single three-paper set supports formative testing. Four-condition comparative testing needs different matched sets or an explicitly disclosed repeated-exposure design. Do not reuse the same answers and call the resulting speed difference an uncontaminated effect.
