# Coordinator roadmap and completion evidence

The goal remains a reproducible systematic/scoping review workflow across all six priorities. Accepted gates establish specific software behavior; they do not establish the methodological validity of an individual review. Coordinator owns interfaces, ticket order, evidence review, and commits. Implementation, Retrieval, and Evaluation receive bounded tickets with separate file ownership.

## Current requirement audit

| Priority | Authoritative evidence | State / remaining requirement |
| --- | --- | --- |
| Persistent projects, protocol/eligibility, search records | ReviewStore, review CLI, 68 independent ledger acceptance cases; durable receipt/BLOB history | Accepted for saved imports and PubMed execution provenance. |
| Biomedical discovery and database imports | JSON/RIS/PubMed XML importers; PubMed adapter; 76 capture, 69 integration, 28 CLI independent cases | Capture, verified ledger integration, and offline replay accepted against synthetic responses; live compatibility and comprehensive search coverage are not claimed. |
| Record deduplication and report/study linkage | DOI/PMID and conservative fallback tests; raw occurrences; 40 API and 63 CLI independent linkage cases | Record identity and explicit manual many-to-many study linkage accepted; revisions/conflicts preserve history. |
| Screening and reconciled counts | Append-only screening/retrieval events; 13-report fixture; six-included-report/three-study fixture | Report counts and conditional distinct-study totals accepted; incomplete links keep final study count null. |
| Verified structured extraction | 47 source, 42 evidence and 25 CLI implementation cases; 68 source, 81 evidence and 86 CLI independent cases; executable eight-block offline guide | Source versions, exact quotations, human-entered values/context/appraisals, immutable hashed revisions, distinct verification/adjudication and conditional verified exports accepted. |
| Evaluated medical retrieval/synthesis exports | Original three CC BY 4.0 snapshots; 18 questions/23 passages/43 quotes independently reviewed; 64 independent operational/metric/receipt cases; preserved development selection and held-out failure; three fresh source-disjoint snapshots | Source integrity, operational candidate retrieval and verified exports accepted. V1 quality fails at 4.5/7 support; the optional context method passes original development at 7/7 but fails fresh document-disjoint quality at 4.5/9 support and 3/9 complete. 55 new independent cases pass. Both failed quality gates remain visible; no threshold/gold/code/default change or held-out tuning. |

The two independent integrated-review cases pass exact three-run/21-occurrence/13-record totals, six included reports/three studies, three verified current rows, all 29 export files, deletion/reopening/portable PubMed replay and an actual WAL snapshot spanning search, screening, linkage, source and evidence changes. Coordinator reviewed code and literal evidence; the final clean staged release check passes 1,121 tests plus both source/gold checker pairs, with five existing SWIG warnings. This core workflow gate does not accept the failed medical retrieval quality gate.

## Order after PubMed integration

1. **Study linkage:** introduce stable study IDs and manual report/study associations with reviewer, reason, revisions, and source identifiers. Multiple reports can belong to one study; the model must also represent a report covering multiple studies. Do not infer study independence from DOI/title or discard secondary reports. Included-study totals must expose incomplete linkage instead of assuming one study per report. Coordinator has frozen the next API/count/export ticket; independent fixtures precede implementation.
2. **Verified extraction:** associate source documents/versions with reports, retain source hashes and locators, and store structured findings with exact source quotations. Edits create revisions and invalidate earlier verification. Distinct reviewer confirmation/adjudication is explicit. Export verified evidence separately from proposals and unresolved conflicts, preserving all history. No automated clinical claims or pooled effects in this gate.
3. **Medical retrieval evaluation:** freeze a small, licensed, real medical-source corpus with quantitative, population, follow-up, negation and multi-passage questions. Retrieval produces passages with stable source anchors. Evaluation independently checks anchor validity and reports retrieval failures, including no-answer cases; synthetic test success cannot substitute for this evidence. Choose the default using the frozen development criteria before running held-out ranking, then assess the selected method without tuning on held-out failures. The current three-article corpus does not establish cross-report study truth.
4. **Integrated review gate:** execute one temporary end-to-end review from source imports through linked studies, screening, source-anchored extraction/verification, and exported counts/evidence. Independently calculate record/report/study totals and check exports can be reproduced from preserved source bytes without network calls. Refresh legacy regression and clean staged-checkout tests before each commit.

This ordering addresses report/study duplication before extracting or combining results. [Cochrane's data-collection guidance](https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-05) distinguishes study-level information from report-level sources and describes reconciling multiple reports and independently collected data. The engine must preserve those distinctions; review-specific protocol and reviewer expertise remain inputs.

## Handoff discipline

Each ticket names owned files, changed facts/interfaces, acceptance criteria, and one focused validation command. Evaluation reports independent expected truth, observed results, defects, and limits. Coordinator reviews failures before assigning the next fix or gate. Preserve unrelated local work and generated user data; only reviewed milestone files enter commits. A green narrow gate does not complete the broader roadmap.

## Release decision and next priority

The requested one-project import/history/deduplication/screening/reconciled-export milestone passes independently. This release also supplies study linkage, source/evidence revision verification, and auditable experimental passage candidates. It does not accept medical retrieval quality or automated synthesis. Root independently recomputed every fresh OR/AND own-quotation score before accepting the failure report.

The next highest-value retrieval ticket should address missing complete table/long-paragraph support, missing companion passages and unrecovered limitation contexts. Freeze one bounded generic candidate before ranking, verify its software/provenance behavior, compare it only on permitted development data, then use separately authored fresh source-disjoint held-out evidence after prospective selection. Neither v1 nor v2 held-out files may become a tuning or acceptance set. Existing failed results and exact source anchors remain permanent evidence. No further algorithm or source-acquisition experiment is included in this release.

Planned handoffs for the subsequent retrieval cycle (outside this release):

| Owner / ticket | Owned files | Acceptance criteria |
| --- | --- | --- |
| Implementation I9 | New candidate in src/review/retrieval.py and its focused tests; bounded CLI changes if needed | One frozen full-block/table-support hypothesis; preserve existing defaults/traces, exact anchors, read snapshots and no ledger writes. No medical gold inspection or ranking. |
| Retrieval R20 | New licensed source and gold fixture folders | Independent, source-disjoint question/support truth fixed before candidate ranking; quantify multi-passage, table, population and source-grounded no-answer coverage; preserve known corrections and every byte pin. |
| Evaluation E10 | New independent acceptance cases, versioned harness and report | Independently verify code math/provenance and all gold semantics, review permitted development only, require root receipt before selected-only fresh held-out, and preserve any failed quality result. |
