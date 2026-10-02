# Coordinator roadmap and completion evidence

The goal remains a reproducible systematic/scoping review workflow across all six priorities. Accepted gates establish specific software behavior; they do not establish the methodological validity of an individual review. Coordinator owns interfaces, ticket order, evidence review, and commits. Implementation, Retrieval, and Evaluation receive bounded tickets with separate file ownership.

## Current requirement audit

| Priority | Authoritative evidence | State / remaining requirement |
| --- | --- | --- |
| Persistent projects, protocol/eligibility, search records | ReviewStore, review CLI, 68 independent ledger acceptance cases; durable receipt/BLOB history | Accepted for saved imports and PubMed execution provenance. |
| Biomedical discovery and database imports | JSON/RIS/PubMed XML importers; PubMed adapter; 76 capture, 69 integration, 28 CLI independent cases | Capture, verified ledger integration, and offline replay accepted against synthetic responses; live compatibility and comprehensive search coverage are not claimed. |
| Record deduplication and report/study linkage | DOI/PMID and conservative fallback identity tests; raw occurrences retained | Record deduplication accepted; explicit auditable study linkage still missing. |
| Screening and reconciled counts | Append-only review/adjudication/retrieval events; hand-computed 13-report fixture; seven identities | Accepted for reports; study counts require the linkage gate. |
| Verified structured extraction | Existing passage labels/pages only | Missing structured values, anchored quotations, revisions, reviewer verification, and evidence-only export. |
| Evaluated medical retrieval/synthesis exports | Existing generic/neural-network retrieval work outside current ownership | Missing a real medical-source evaluation set and evaluated retrieval gate; verified evidence exports still missing. |

## Order after PubMed integration

1. **Study linkage:** introduce stable study IDs and manual report/study associations with reviewer, reason, revisions, and source identifiers. Multiple reports can belong to one study; the model must also represent a report covering multiple studies. Do not infer study independence from DOI/title or discard secondary reports. Included-study totals must expose incomplete linkage instead of assuming one study per report. Coordinator has frozen the next API/count/export ticket; independent fixtures precede implementation.
2. **Verified extraction:** associate source documents/versions with reports, retain source hashes and locators, and store structured findings with exact source quotations. Edits create revisions and invalidate earlier verification. Distinct reviewer confirmation/adjudication is explicit. Export verified evidence separately from proposals and unresolved conflicts, preserving all history. No automated clinical claims or pooled effects in this gate.
3. **Medical retrieval evaluation:** freeze a small, licensed, real medical-source corpus with quantitative, population, follow-up, negation and cross-report questions. Retrieval produces passages with stable source anchors. Evaluation independently checks anchor validity and reports retrieval failures, including no-answer cases; synthetic test success cannot substitute for this evidence. Changes must be assessed on held-out questions before choosing the default.
4. **Integrated review gate:** execute one temporary end-to-end review from source imports through linked studies, screening, source-anchored extraction/verification, and exported counts/evidence. Independently calculate record/report/study totals and check exports can be reproduced from preserved source bytes without network calls. Refresh legacy regression and clean staged-checkout tests before each commit.

This ordering addresses report/study duplication before extracting or combining results. [Cochrane's data-collection guidance](https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-05) distinguishes study-level information from report-level sources and describes reconciling multiple reports and independently collected data. The engine must preserve those distinctions; review-specific protocol and reviewer expertise remain inputs.

## Handoff discipline

Each ticket names owned files, changed facts/interfaces, acceptance criteria, and one focused validation command. Evaluation reports independent expected truth, observed results, defects, and limits. Coordinator reviews failures before assigning the next fix or gate. Preserve unrelated local work and generated user data; only reviewed milestone files enter commits. A green narrow gate does not complete the broader roadmap.
