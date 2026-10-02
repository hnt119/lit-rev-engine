# Coordinator roadmap and completion evidence

The six foundations now have accepted, bounded software gates for a reproducible systematic/scoping review workflow. The requested one-project import/history/deduplication/screening/reconciled-export milestone passes independently. Acceptance describes the observed software behavior and frozen pilot; individual review protocols, comprehensive search coverage and clinical judgments remain reviewer inputs.

The coordinator owns architecture, interfaces, ticket order, acceptance criteria, evidence review and release decisions. Implementation owns bounded operational changes, Retrieval owns source acquisition/gold/provenance, and Evaluation independently checks expected truth and observed results. All six foundations are covered below; remaining limitations are explicit rather than silently counted as implemented.

## Requirement audit

| Priority | Accepted evidence | Practical boundary |
| --- | --- | --- |
| Persistent projects and search histories | ReviewStore/CLI; 68 independent ledger cases; exact import/search receipts, raw occurrences and retained bytes | Saved review question, protocol and eligibility metadata are user supplied. Unknown search dates/query fields remain unknown. |
| Biomedical discovery and imports | Strict JSON/RIS/PubMed XML; 76 capture, 69 integration and 28 CLI independent cases; portable offline replay | PubMed behavior tested against synthetic responses; no live-compatibility or comprehensive strategy claim. Searches exceeding 10,000 require a separately validated workflow. |
| Record deduplication and report/study links | DOI/PMID conservative identity and atomic import tests; 40 API and 63 CLI independent linkage cases | Explicit many-to-many study identities preserve reports. Incomplete/conflicting associations keep final study totals null. Manual citation merging remains future work. |
| Screening and reconciled counts | Append-only reviewer decisions/retrieval status, conflicts/adjudication, reasons and prerequisites; independently calculated report/study totals | Declared identities provide an audit trail, without authentication or enforced reviewer quorum. Stage reopening remains future work. |
| Verified structured extraction | Retained TXT/JATS/PDF sources; immutable exact-anchor finding/appraisal revisions; distinct verification/adjudication; independent source/evidence/CLI checks and eight-block offline guide | Human-entered values and judgments require original-source review. Source replacement and edits invalidate verification; no automatic clinical finding or pooled effect. |
| Evaluated medical retrieval and verified exports | Three frozen source-disjoint pilots; v3 whole-block candidate passes its prospective gate; exact anchors/scope/read-only checks; conditional verified exports | Optional reviewer-facing retrieval: 85.2% mean support, 6/9 complete positives, three incomplete positives and weak null-context recovery. No automatic answerability, clinical validation or cross-report synthesis claim. |

The two independent integrated-review cases pass exact three-run/21-occurrence/13-record totals, six included reports/three studies, three verified current rows, all 29 export files, source deletion/reopening/portable PubMed replay, and an actual WAL snapshot across search, screening, linkage, source and evidence changes. Export counts reconcile from one retained ledger snapshot. [Integrated evaluation](integrated-review-evaluation.md) records literal expected totals and reproduction evidence.

The final clean staged-checkout release gate passed **1,240 tests and 31 subtests in 77.00 seconds**, with five existing PyMuPDF SWIG warnings. All four licensed-source archive checkers and all three frozen medical-gold checkers passed. API credentials were removed and model downloads disabled. No medical ranking was rerun by this gate. The checkout contains only reviewed release files; unrelated local experiments remain outside the commit. Subsequent edits record this evidence in documentation only.

## Retrieval release decision

V1 and v2 failed their frozen medical-quality gates. Their questions, source snapshots, gold, prospective receipts and results remain unchanged. These failures led to one generic v3 hypothesis: return complete canonical blocks while retaining the accepted BM25 and separate preceding-paragraph context rule. Existing methods and the BM25 default remain identical.

Implementation I9 passed whole-block math, long paragraph/table, padded Unicode TXT, physical PDF-page, scope, integrity and snapshot checks. Evaluation E10 added 43 independent cases; all 119 earlier retrieval acceptance cases remained green. Retrieval R20/R22/R23 supplied three further DOI-disjoint licensed articles, source-first truth and source caveats. Evaluation E11 accepted all 156 canonical blocks, nine tables, 26 declared passages and 58 exact quote spans before ranking. The fresh set has nine quantitative answerable questions, eight necessary distinct-block AND requests and three sound main-article-scoped nulls. All identified sufficient alternatives remain preserved.

The coordinator froze code, parameters, sources, gold, metrics, harness, tests and contract before development. E12 compared only the original nine development questions; both reference and candidate retained 7/7 complete positives and identical required-quotation ranks. MRR remained 0.7380952380952381; block-position regressions and a misleading result were disclosed. The coordinator selected the eligible whole-block method before fresh QA inspection or ranking.

E13's first setup attempt stopped before the first query because the harness expected a top-level publisher URL absent from the frozen manifest. R24 added a separate metadata-only held-out wrapper; E14 independently accepted 69 synthetic repair cases plus 31 subtests, with all 162 earlier retrieval cases unchanged. A new coordinator repair receipt pins that wrapper and both new test files before the first actual fresh grade. No original frozen file, question, metric, parameter or selection was changed.

E13b ran the selected method once and passed all six predeclared conditions: 0.8518518518518519 mean support coverage, 6/9 complete positives, 60/60 own anchors, 36/36 scoring-context anchors, exact scope isolation and the declared nine-positive denominator. Hit is 1.0 and MRR is 0.8888888888888888; neither substitutes for complete support. Three positives retain partial support (2/3, 1/2 and 1/2). All three nulls return candidates; only 1/4 declared no-answer context quotes is recovered and two null queries return a declared hard negative. Read-only and same-ledger repetition/reopening checks pass. Root independently reconstructed every own/context anchor and OR/AND metric from original sources, validated repair/result binding and confirmed all four earlier result hashes remain unchanged.

This accepts the bounded v3 pilot and the six technical foundations. It does not compare retrieval quality across unlike source sets or validate clinical judgments. The [v3 evaluation](medical-retrieval-v3-evaluation.md), [full result](medical-retrieval-held-out-v3.json), [selection](medical-retrieval-selection-v3.json) and [repair receipt](medical-retrieval-v3-schema-repair.json) preserve evidence and limits. No further ranking, sweep, held-out tuning or default change followed the first actual grade.

## Next highest-value step

Run one protocol-defined review pilot with human reviewers. The current fixtures establish reproducible mechanics; a real pilot should test whether protocol-specific searches, duplicate/conflict resolution, report/study links and verified extraction remain usable and complete. Its review question, databases, eligibility rules and extraction fields must come from the review team. Additional algorithm experiments have lower immediate value than that workflow evidence.

These are proposed next-cycle tickets, beyond the accepted foundation release:

| Owner / ticket | Files / changed facts | Acceptance criteria |
| --- | --- | --- |
| Implementation I10 | A new isolated pilot guide and minimal fixes demonstrated by that pilot | Start one saved project, preserve supplied protocol, execute/import searches, screen/link/verify and export without undocumented state changes. Fix a demonstrated bug before expanding features. |
| Retrieval R25 | New attributed pilot search/source receipts, separate from frozen benchmarks | Capture exact strategies/dates/limits and raw results from the team's specified databases; preserve source identity/version/permissions; disclose coverage gaps. No benchmark-derived query selection. |
| Evaluation E15 | New pilot acceptance report and narrowly necessary regression cases | Independently reconcile occurrences/records/reports/studies; audit exclusions, reviewer conflicts and verified quotations; reproduce exports after deleting originals; report missing workflow evidence. |

No live search or new pilot topic is implied by these proposals. Frozen benchmark truth remains evaluation evidence. [Cochrane's data-collection guidance](https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-05) supports retaining study/report distinctions and reconciling independently collected data; the engine records that work rather than making those judgments automatically.

## Handoff discipline

Each ticket names owned files, changed facts/interfaces, acceptance criteria and one focused validation command. Evaluation reports independent expected truth, observed results, defects and limits. Root reviews that evidence before selecting the next ticket. Preserve unrelated local files and generated user data; only reviewed files enter commits. The clean staged regression gate has passed; authorized commit/push publishes the reviewed release on `codex/review-ledger`.
