# Project source retrieval: independent evaluation

Status: the coordinator accepted the 58-case operational/metric gate and selected BM25 as the software default from development using the prospective rule. The authorized BM25 held-out run **fails the frozen medical retrieval quality gate**: mean support coverage is 4.5/7 (64.29%), below 75%. Four complete questions meet the separate ≥4/7 requirement. Anchor validity, current-source/project/scope isolation, determinism and read-only behavior pass. The coordinator independently recomputed and accepted the failed result as evidence, without accepting medical retrieval quality. No method, gold, threshold or ranking parameter was changed after observing held-out failures.

Evaluation owns `tests/test_project_retrieval_acceptance.py`, `tools/evaluate_medical_retrieval.py`, this report and the versioned result JSONs. Implementation supplied 29 new synthetic retrieval cases and reported 146 focused passes including legacy cases. Evaluation changed no operational files, original questions, sources, frozen labels, parser behavior, existing data, settings, external benchmark/evaluation/report work or Git state. The coordinator owns selection and next-ticket decisions; clean staged regression remains its separate gate.

## Frozen truth and evaluation sequence

The three licensed, attributed publisher XML snapshots are COACH, Whitehall II and RAPTOR-C19. Their complete accepted primary-article block counts are 79, 88 and 48. The pilot has 18 independently drafted questions, 23 source passages and 43 exact quotation spans, with nine questions per split: seven answerable and two no-answer. The question-level split shares articles and some passages, so it does not establish document-level generalization. Source attribution and acquisition/version caveats remain in `tests/fixtures/medical_sources/` and the pilot manifest.

Before ranking, Evaluation independently resolved every original local-tag/sibling XML path with ElementTree, checked each canonical block/locator and every half-open Unicode quotation, and compared all expected values, population/arm/timepoint context, negation and no-answer statements with complete original source passages. No source-fact or support defect was found. The coordinator accepted that review and prospectively froze five question/anchor/manifest files plus methods, parameters, metrics and thresholds in `tests/fixtures/medical_retrieval/freeze.json`. Original draft status strings were preserved in the byte-pinned files; the coordinator freeze is the superseding acceptance record.

The source/gold checker passed frozen pins before each authorized evaluation. Both methods were evaluated on development only. The coordinator then reviewed per-question evidence and saved `docs/medical-retrieval-selection-v1.json` before authorizing held-out BM25 only. The harness validates that receipt's development/freeze hashes, pre-ranking status, chosen method and frozen selection rule before any held-out search. Six independent receipt cases reject missing/post-ranking receipts, changed input hashes, a different method, or a changed rule without executing ranking. No development rerank or held-out token-overlap run occurred.

| Immutable evaluation artifact | SHA-256 |
| --- | --- |
| Development v1 | f1275c258e8b1cfce756788fe41b3c089729978a304fcd781758a390a7fb7075 |
| Held-out v1 | c7c2765a25576cadeb3ab9bef7d5be30c9092b3df3f0b594c9d7dd60a85c37a0 |
| Prospective freeze | e0b8b7581c16ad2e96df19ba93e7d77a4252001ba774b96eec3c4dd842b2b0b7 |

The result files retain complete operational traces, exact anchors/locators, source manifests/hashes, query text, scores/ranks, per-question gold quote coverage, support sets, expected source-reported answers, failures and no-answer context/hard negatives. Operational traces retain real ledger UUIDs. Traces repeat byte-for-byte within the same reopened ledger; fresh ledgers generate different IDs, so metric reproducibility does not imply cross-ledger UUID identity. Each evaluation's ledger is temporary, and retrieval never writes search/evidence/reviewer events.

## Metric truth and operational acceptance

Windows contain at most 200 `\S+` words, overlap by 40, retain original first/last character bounds and add a final window only when it adds words. Windows never cross blocks, documents or reports. Exact casefolded Unicode tokens and the fixed stop words preserve numeric and negation terms. Token overlap counts distinct matching query terms. BM25 uses the frozen k1=1.2, b=0.75 and positive-log IDF over all eligible snapshot windows. Scores are neither support probabilities nor answerability judgments.

The independent metric code treats outer support sets as OR alternatives and passages within one set as AND requirements. A required passage is covered only if every question-specific quote is fully contained in an exact returned window for its same document/source/block; different windows may contain different complete quotes. A clipped quote or a quote whose halves appear in separate windows cannot establish its full anchor. Per-question coverage is the best alternative's fraction of covered passage requirements. Completeness needs an entire alternative set. Hit/MRR use the first rank containing any required gold quote and therefore can pass while complete support fails. No-answer questions are excluded from the seven-question answerable denominator.

The final **64 independent cases** comprise the accepted 58 operational/metric cases plus six receipt safeguards. They prove:

- An analytically hand-calculated two-document BM25 case, distinct token-overlap scores, stop-word-adjusted lengths, query-term reordering/repetition determinism, original Unicode/casefold/negation/numeric text, exact 200/40 character windows, boundary tails, creation-order tie breaks and large positive top_k without an arbitrary cap.
- Exact manifest keys/fields and method/version/parameters; source/report ownership, active version, current screening and linkage provenance; explicit included versus all_attached scope; foreign-project, inactive, excluded and unattached-source isolation. Pending/conflicted study linkage is visible provenance and is never inferred into a study or verification.
- Blank/invalid queries/options fail atomically. Empty effective queries retain selected manifests/index size and validate integrity. Corrupt selected original bytes/blocks/digests and later canonical DOI/PMID contradictions reject before returning candidates, including stop-word-only queries; corrupt unselected inactive/excluded bytes do not leak into included scope.
- TXT/JATS/PDF candidates have exact canonical substring bounds and typed locators, including complete tab-separated tables and physical PDF pages with blank pages skipped as windows. A caller can explicitly enter a proposal from a candidate anchor, but retrieval itself creates no evidence or verification.
- Manifest/trace/source bytes survive export, original-file deletion and reopening; identical subprocess CLI traces and complete logical ledger fingerprints remain unchanged. Invalid CLI options create no output artifact. A real WAL second writer changes source version and eligibility after the reader captures records; the trace retains the entire old snapshot while the next read sees the new version/exclusion.
- A guarded fresh CLI process retrieves without models, settings, dotenv, a PDF parser, live indexes or network. Independent synthetic metric cases exercise OR alternatives, AND completeness, multiple required quotes/windows, wrong identity/block, clipped spans, rank-six exclusion, separate no-answer denominators and prospective method ordering/tie behavior.

The benchmark validator also compares each selected manifest to current canonical reports, active documents, exact source/parser metadata and linkage state, and validates every returned anchor/version/ownership. All three active included sources and **241 indexed windows** appear consistently. Logical ledger fingerprints before/after rankings are unchanged; every trace repeats in the same ledger and after reopening.

## Development comparison and selection

Both development methods meet the prospectively frozen eligibility rule: coverage ≥75% and ≥4 complete questions out of seven. They tie on coverage/completeness, and BM25 wins on MRR under the fixed ordering. The coordinator selected BM25 before held-out ranking.

| Development measure | Token overlap | BM25 |
| --- | ---: | ---: |
| Any required quote Hit@5 | 6/7 (85.71%) | 6/7 (85.71%) |
| MRR@5 | 0.647619 | 0.785714 |
| Best-alternative support coverage@5 | 6/7 (85.71%) | 6/7 (85.71%) |
| Complete questions@5 | 6/7 | 6/7 |
| Exact returned anchors | 45/45 | 45/45 |
| No-answer queries with candidates | 2/2 | 2/2 |
| Declared no-answer context quotes recovered | 1/2 | 1/2 |

| Answerable development question | Overlap first required-quote rank | BM25 first required-quote rank | Coverage, both methods |
| --- | ---: | ---: | ---: |
| dev-coach-01: identification criteria | 1 | 1 | 1 |
| dev-coach-02: arm attrition/deaths | 1 | 1 | 1 |
| dev-whitehall-01: multimorbidity definition | 5 | 1 | 1 |
| dev-whitehall-02: age-50 adjusted association | 1 | 1 | 1 |
| dev-whitehall-03: age-specific sample/follow-up | 3 | 2 | 1 |
| dev-raptor-01: primary-analysis exclusions | 1 | 1 | 1 |
| dev-raptor-02: measured SARS-CoV-2 accuracy | None at five | None at five | 0 |

The shared accuracy failure retrieves the measurement-method paragraph, related primary-analysis/abstract text and manufacturer claims while neither frozen required body/table measured-result alternative is covered. BM25's rank-four abstract does contain measured sensitivity and specificity: its sensitivity interval lower bound is 49.6, whereas the frozen body/table quotation reports 49.8. This internal source discrepancy and the non-exhaustive alternatives matter when interpreting the metric failure; the failure does not mean all measured results are absent. Manufacturer claims rank third under overlap and second under BM25; they cannot supply this prospective study's requested estimates/fractions. Unlabeled/partial related passages are not promoted to complete gold support after inspecting results.

Both no-answer questions return five positive-score candidates. The COACH participant-medication adherence limitation is absent at five; BM25 retrieves team intervention activity at rank two, a predeclared hard negative. The RAPTOR omitted follow-up statement is recovered at rank three by overlap and rank one by BM25. Neither nonempty results nor context retrieval establishes an answer or an automatic abstention policy.

## Selected BM25 held-out result: gate failed

The authorized selected method ran once as an evaluation invocation with unchanged frozen methods/parameters/gold and normal same-ledger repetition/reopening checks. **No tuning followed.**

| Frozen held-out check | Observed | Outcome |
| --- | ---: | --- |
| Mean support coverage@5 ≥0.75 | 4.5/7 = 0.642857 | Fail |
| Complete questions@5 ≥4/7 | 4/7 | Pass |
| Exact anchor validity =100% | 45/45 | Pass |
| Project/active-document/scope isolation =100% | All selected manifests and windows valid | Pass |
| Answerable denominator | 7 | Pass |

Hit@5 and MRR@5 are both 5/7 (0.714286): all five questions with any required quote first hit at rank one, but one has only half its required support. Complete-question rate is 4/7 (57.14%). Both no-answer questions have nonempty candidates and only two of four declared context quotes are recovered.

| Answerable held-out question | First required-quote rank | Support coverage | Complete | Retained finding |
| --- | ---: | ---: | --- | --- |
| held-coach-01: actual/planned randomization | 1 | 1 | Yes | All three declared quotes covered |
| held-coach-02: control rates plus BP definitions | 1 | 0.5 | No | Threshold definition covered; both arm/control-rate quotes missing |
| held-whitehall-01: conditional long-sleep sensitivity analysis | 1 | 1 | Yes | Exact population/HR/interval/p context covered |
| held-whitehall-02: multistate versus posthoc mortality | None at five | 0 | No | Neither required results passage covered |
| held-raptor-01: eligibility and baseline characteristics | 1 | 1 | Yes | Population quote at rank two and both characteristic quotes at rank one |
| held-raptor-02: omitted planned components | 1 | 1 | Yes | Exact omitted-follow-up/serology context covered |
| held-raptor-03: measured influenza B accuracy | None at five | 0 | No | Neither measured paragraph/table alternative covered; manufacturer claims rank three |

The COACH control-rate question retrieves the BP definition at rank one, a blinding paragraph, a different HTN subgroup pattern, and two Whitehall passages; these cannot replace the requested COACH/eCAU twelve-month rates. Whitehall mortality retrieval favors multistate methods, objectives and general summaries/discussion rather than the two required analysis-specific result passages. Influenza B retrieval favors calculation methods, abstract and related results, manufacturer claims and kit usability rather than the measured estimates and PCR denominator. The exact windows and scores for these failures remain in the result JSON.

For no-answer held-coach-03, both declared component-only limitation quotes are covered at rank one. For held-whitehall-03, neither the observational cohort nor residual-confounding limitation quote is covered at five. Candidate passages remain explicitly candidates and produce no clinical assertion, answer, evidence revision or verification event.

## Commands and limits

```text
.venv/bin/python tests/fixtures/medical_retrieval/verify.py
PASS: 3 pinned sources; 23 passages; 18 questions; 43 exact spans; freeze verified

.venv/bin/python -m pytest tests/test_project_retrieval_acceptance.py -q
58 passed, 5 warnings in 2.10s  # Initial accepted operational/metric gate
64 passed, 5 warnings in 1.68s  # Plus authorized receipt safeguards

.venv/bin/python tools/evaluate_medical_retrieval.py --output docs/medical-retrieval-development-v1.json

.venv/bin/python tools/evaluate_medical_retrieval.py --split held-out --selection docs/medical-retrieval-selection-v1.json --output docs/medical-retrieval-held-out-v1.json
```

The five warnings are existing PyMuPDF SWIG deprecations. No operational defect, evaluator expectation correction or relaxed assertion was needed. The final tests, harness and result artifacts are frozen for coordinator review; there was no shared broad regression or Git operation by Evaluation.

This is a small three-article, agent-authored software pilot with non-exhaustive support labels and shared-document question splits. The corpus contains no established multiple-report study, so multi-passage questions cannot validate cross-report retrieval. BM25's selected software interface passes integrity/isolation gates while its held-out retrieval quality fails the prospective threshold. Treating that failure as acceptance, tuning on these held-out questions or changing frozen labels to improve scores would invalidate this pilot. The coordinator must decide the next bounded ticket and any fresh independent evaluation needed for a changed method.

## Coordinator release check

Root reviewed the code and independent evaluation evidence, then tested a temporary checkout containing only the staged release files. Both licensed-source verifiers and both frozen question/anchor verifiers passed. With AGNES, NCBI and OpenAI credentials absent and model downloads disabled, the complete suite passed **1,121 tests, five existing PyMuPDF SWIG warnings, in 75.56 seconds**. No medical ranking was rerun. This release accepts the core review workflow and operational passage interfaces; both medical retrieval quality failures remain unaccepted and preserved. Unrelated local benchmark files were excluded from this release rather than subtracted from its test result.
