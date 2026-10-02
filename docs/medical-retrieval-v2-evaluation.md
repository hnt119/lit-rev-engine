# Medical retrieval v2: independent evaluation

Status: synthetic software and harness gates pass, independent fresh source/gold semantic review is complete, and the context candidate passes strict development eligibility. The selected-method-only fresh held-out run **fails the frozen quality gate**: support coverage is 4.5/9 (50%) and only 3/9 answerable questions are complete, below 75% and six complete questions. Exact own/context anchors and project/current-source/scope isolation pass. No tuning, reranking, default change or gold/source/code change follows that failure. The immutable v1 result files, gold, harness and thresholds remain unchanged.

Evaluation owns `tests/test_project_retrieval_v2_acceptance.py`, `tools/evaluate_medical_retrieval_v2.py`, this report and the versioned result JSONs. The contract is `docs/project-retrieval-v2-milestone.md`. No operational code, source/gold bytes, README, settings, user data, installs or Git state was changed.

## Synthetic software and harness evidence

The independent suite has **55 cases**, including actual CLI subprocesses and an explicit WAL second writer. It verifies:

- A literal three-paragraph BM25 calculation with augmented representation lengths 3/5/4, average length 4, full document frequencies and exact term frequencies. Distinct query-token accumulation, deterministic ordering, repeats and no ledger writes are checked. A separate 361-word target has three own windows with the same context appended exactly once per window; all four representation lengths and scores are independently calculated.
- Exact suffixes at 1/79/80/81/100 words, original canonical Unicode offsets, casefold matching and exclusion of words outside the last 80. Context selects the closest preceding paragraph within the exact same immediate XML parent, including intervening tables/titles and nested/sibling sections. A target never borrows itself; a nearer unrelated paragraph replaces an older matching paragraph.
- Separate own table anchors for context-only lexical matches. The frozen OR/AND metric counts only own anchors: a required quotation appearing solely in `scoring_context` provides zero support. Abstract paragraphs retain their own parent rules; titles, TXT and PDF have empty contexts. Typed locators, source/block/parser identity and exact source substrings are checked for own and context anchors.
- Project/report/document/version and included/all-attached isolation; current manifest provenance; rejection of all four selected source-integrity corruptions even for a stopword-only query; and rejection of a late canonical PMID contradiction. Candidate calls append no findings or reviews.
- An actual SQLite WAL read snapshot across a concurrent source replacement and full-text exclusion. The reader returns the complete old trace/context; the next included read excludes it and the next all-attached read uses only the new source/context.
- Unchanged literal v1 BM25/overlap scores, IDs, default method and absence of new context fields. Actual fresh CLI repeats and reopening reproduce exact candidate traces without rows changing. A separate guarded fresh process forbids model, RAG settings, dotenv and PDF imports and network access while exercising the actual candidate CLI.
- Independent harness validation rejects missing, self-borrowed, clipped, duplicated and wrong-locator contexts and changed parameters. Development requires all seven answerable questions complete, mean coverage 1.0, at least one declared no-answer context quote, and 100% own/context anchor validity and scope isolation. Synthetic selected-receipt cases reject missing/late receipts, baseline substitution, changed code bytes/pins, changed parameters/rules, incorrect frozen/development hashes, inconsistent aggregate metrics and an ineligible candidate.

Observed focused regression:

```text
.venv/bin/python -m pytest tests/test_project_retrieval_v2_acceptance.py tests/test_project_retrieval_acceptance.py -q
119 passed, 5 warnings in 2.48s
```

This combines 55 new v2 cases with the unchanged 64 v1 operational/metric/receipt cases; it performs synthetic retrieval only. The five warnings are existing PyMuPDF SWIG deprecations. The initial v2 run reported 23 passes and four evaluator suffix-setup failures because it expected mixed raw XML whitespace in canonical paragraphs. Accepted I6a JATS text collapses whitespace. Evaluation reported the error before correcting the independently expected canonical text to the literal joined words; all five word-boundary cases and exact Unicode/prefix-exclusion assertions remain intact. The corrected 27-case operational subset passed in 0.72s. Adding the harness guards produced 55 passes in 0.84s; the final guarded-process and unchanged-v1 regression is recorded above. No operational defect or relaxed truth was found.

## Fresh source/gold review without ranking

The three archived primary-article sources have new, document-disjoint DOIs and source attribution/version/correction metadata. Independent byte length/hash and primary own-DOI checks agree with the accepted source manifest. Direct original-XML path resolution and paragraph/table text reconstruction, independent of ranking, match all **24** provisional passages and all **31** half-open Unicode quotation spans. Accepted canonical block counts are **86/82/44** for the three sources. Original table labels, cells/foot text and nearest section titles are checked independently.

The finalized draft has **12 questions**, four per source, with **9 answerable / 3 source-grounded no-answer**, **6 multi-passage AND** questions and **5 quantitative** questions. Evaluation has read each requested population, timepoint, analysis, estimate/interval/denominator, outcome and negation distinction against its original source passages and broader archived methods, results, discussion, limitations, abstract and relevant table context. All declared complete-support alternatives and explicit no-answer limitations have been checked; no semantic or anchor defect has been observed. Printed source discrepancies are retained with explicit scope qualifiers rather than silently corrected. Alternatives remain a small agent-authored enumeration, without an exhaustive-support or clinical-validity claim. Unacquired supplemental data and figure images supply no gold claims.

Before selection, the coordinator and Implementation receive only review counts, categories, file hashes and bounded defect status, not fresh question/answer content. Final Retrieval anchor/checker/README bytes were reviewed before the prospective coordinator freeze. The independent checker passed with historical and effective Python 3.12.7 and unchanged historical anchors:

```text
.venv/bin/python tests/fixtures/medical_retrieval_v2/verify.py
PASS: 3 pinned sources; 24 exact main-article passages; 12 fresh held-out questions
(9 answerable, 3 no-answer; 5 quantitative, 6 AND); 31 exact Unicode quote spans.
Anchor reconciliation ready; pilot remains unfrozen. No ranking/model/index/network.
```

Evaluation independently confirmed these final file pins:

| File under tests/fixtures/medical_retrieval_v2 | Bytes | SHA-256 |
| --- | ---: | --- |
| manifest.json | 13697 | fabddc904f9e979a792c8106bcb846cc42d7fd18e93c7a273165ba3873e4ab1d |
| held-out.json | 33550 | 90a043e5b67f8425e6a6c51fc7c337ad5019dead2d443ce003f252704593d7c6 |
| passages.json | 67412 | b15df2ba31d550dfd316e482293d0024b36a63e57ecd4a578359ae8a5d8a7f50 |
| anchors.json | 37971 | 2d442f91618a333561f3a77f45fd93aa179544705d74e6138a361038ddacfb29 |
| verify.py | 19411 | c34284edb3573605ba67a6705b2d9079bc2843bedf007d7a46b47e2cdae8a1c0 |
| README.md | 8712 | e75c26d810b04dbad18997b71d88281186fc3372ae7693b5004129868dbbb1d7 |

The coordinator accepted the independent semantic review without reading the fresh QA content, then froze gold/source/code/parameters at **2026-10-02T20:13:33.093194+00:00**, before any v2 medical ranking. `tests/fixtures/medical_retrieval_v2/freeze.json` has SHA-256 **5cb33360cc358350453e58bffe1ace790b21f9824ecd8b461c522dd6a1c4cd8a** and declares zero prior ranking runs. Both source/gold checkers verify the prospective freeze; historical metadata remains unchanged.

## Authorized development result

The coordinator explicitly released one invocation on the original nine development questions and old three sources, comparing the unchanged BM25 reference with the single context candidate:

```text
.venv/bin/python tools/evaluate_medical_retrieval_v2.py --output docs/medical-retrieval-development-v2.json
```

The result is **439991 bytes**, SHA-256 **2cb7bcfa1768b440768ed1fc6a0f7998fad810bdf9f0295e0ccc9c458c0c6b11**. It retains all eighteen per-question rows and complete own/context traces, source manifests, hashes, parameters, ranks, scores, hard negatives and failures. Only the original development split was ranked; no parameter, source or gold change followed the result.

| Development metric | BM25 reference | bm25_context |
| --- | ---: | ---: |
| Answerable denominator | 7 | 7 |
| Mean support coverage at five | 6/7 (85.71%) | 7/7 (100%) |
| Complete questions at five | 6 | 7 |
| Any-required-quote Hit at five | 6/7 | 7/7 |
| Mean reciprocal rank at five | 0.785714 | 0.738095 |
| No-answer declared context quotes recovered | 1/2 | 1/2 |
| Exact own anchors checked | 45/45 | 45/45 |
| Exact scoring-context anchors checked | 0 present | 24/24 |
| Indexed own windows | 241 | 241 |
| Project/active-source/scope isolation | 100% | 100% |
| Same-ledger repeat/reopen and no writes | Pass | Pass |

The independently frozen gate requires all seven answerable questions complete, mean coverage 1.0, at least one no-answer context quote and exact own/context anchors and scope isolation. The candidate meets every check. The original six complete questions remain complete; the RAPTOR accuracy question gains the required body-result support at rank two. This development eligibility is permission to seek coordinator selection, not fresh held-out or medical validation.

| Original development question | BM25 first required quote rank | Candidate rank | Candidate support |
| --- | ---: | ---: | ---: |
| dev-coach-01 | 1 | 1 | Complete |
| dev-coach-02 | 1 | 3 | Complete |
| dev-whitehall-01 | 1 | 1 | Complete |
| dev-whitehall-02 | 1 | 1 | Complete |
| dev-whitehall-03 | 2 | 3 | Complete |
| dev-raptor-01 | 1 | 1 | Complete |
| dev-raptor-02 | None at five | 2 | Complete |

There are two first-support-rank regressions: COACH's second question moves 1→3 and Whitehall's third question moves 2→3. Their own-anchor support remains complete. Those losses outweigh the new reciprocal-rank contribution in the average MRR; the prospectively frozen selection gate prioritizes complete support, not a newly selected MRR threshold.

For the RAPTOR accuracy question, the context candidate's first result remains the measurement-method paragraph. Its second own anchor now contains the frozen measured estimates and denominators; its separate preceding-paragraph context does not count toward support. Manufacturer claims remain a hard negative at rank three, compared with rank two under BM25. The measured abstract still appears (candidate rank five, reference rank four) and reports the known 49.6 lower bound rather than the required body/table 49.8. The reference failure means missing the frozen required body/table quotations, not an absence of every measured result in its candidates. Source discrepancy and non-exhaustive alternatives remain disclosed without changing gold.

Both no-answer questions return five positive-score candidates. COACH's participant-adherence limitation remains absent, while its predeclared team-activity hard negative drops out of the candidate top five. RAPTOR's omitted-data context remains recovered at rank one by both methods. Nonempty candidates and source-limitation recovery establish neither an answer nor an abstention policy.

A separate artifact-only comparison confirms all nine BM25 reference traces match the pinned v1 traces after unwrapping v2's `{question_id, trace}` entries, explicitly normalizing fresh project/report/document UUIDs to aliases and excluding the UUID-dependent manifest digest. All other fields, anchors, locators, scores, manifests and parameters compare exactly. Evaluation's first comparison omitted that wrapper distinction and failed; it was reported before correcting the comparison, without changing results or reranking. A draft sentence claiming success was premature and corrected after the check. Operational traces retain real IDs and real manifest digests; raw cross-ledger byte identity is not claimed. Existing repeated/reopened same-ledger identity is the frozen guarantee.

The coordinator independently recomputed the development gate and retained both rank/MRR regressions. Before any fresh QA inspection or ranking, it selected the explicit context method at **2026-10-02T20:15:52.759320+00:00** and wrote `docs/medical-retrieval-selection-v2.json`, SHA-256 **ef05e45a894ba4dafe56b2a9aee6e73ce7c9ef58d71a8427cb010acbb2881ce0**. The receipt pins freeze, development result, implementation bytes, parameters and selection rule; the stable BM25 default remains unchanged.

## Selected-only fresh held-out result

The coordinator authorized one invocation, using only the selected context candidate on the twelve new questions and three new sources:

```text
.venv/bin/python tools/evaluate_medical_retrieval_v2.py --split held-out --selection docs/medical-retrieval-selection-v2.json --output docs/medical-retrieval-held-out-v2.json
```

The result is **342370 bytes**, SHA-256 **5ca5d7148f6fb42bcf2b87890d0132fb6f0371f4ae606c215b84a163eb86890c**. Receipt, prospective freeze and every code/source/gold pin were checked before ranking. BM25 reference and other methods were not ranked on fresh held-out data. Both result files retain their first successful invocation bytes.

| Fresh held-out metric | Selected bm25_context | Prospective requirement |
| --- | ---: | ---: |
| Answerable / no-answer questions | 9 / 3 | 9 / 3 |
| Mean support coverage at five | 4.5/9 (50%) | ≥75% — **fail** |
| Complete answerable questions at five | 3/9 | ≥6/9 — **fail** |
| Any-required-quote Hit at five | 8/9 (88.89%) | Descriptive |
| Mean reciprocal rank at five | 0.75 | Descriptive |
| No-answer context quotes recovered | 0/6 | Separately reported |
| No-answer queries with nonempty candidates | 3/3 | No abstention claim |
| Exact own anchors | 60/60 | 100% — pass |
| Exact scoring-context anchors | 32/32 | 100% — pass |
| Project/active-source/scope isolation | 100% | 100% — pass |
| Indexed own windows | 306 | Frozen construction |
| Same-ledger repeat/reopen and no writes | Pass | Pass |

| Fresh answerable question | First required quote rank | Best support fraction | Missing or recovered support |
| --- | ---: | ---: | --- |
| v2-hold-s1 | 1 | 0 | Only the Table 2 ITT footnote quote is covered; the required caption/primary numeric row are missing from returned own windows. |
| v2-hold-s2 | None | 0 | Neither the complete eligibility quote nor allocation/masking quote group is recovered. |
| v2-hold-s3 | 4 | 0.5 | BP-control result recovered; complete mortality/serious-event quote missing. The Table 2 alternative is also incomplete. |
| v2-hold-c1 | 1 | 0 | The reported hazard-ratio-range quote is recovered, but its required follow-up and epoch-1 model-fit quotes are missing. |
| v2-hold-c2 | 1 | 0.5 | All three vaccination/matching quotes recovered; complete first-infection/population quote missing. |
| v2-hold-c3 | 1 | 1 | Both outcome-specific anxiety result passages recovered. |
| v2-hold-e1 | 2 | 1 | Both test-set count/confusion-matrix and estimate/interval quotes recovered. |
| v2-hold-e2 | 1 | 0.5 | Analysis-population and all exclusion counts recovered; stage/surgery eligibility quote missing. |
| v2-hold-e3 | 1 | 1 | Reference-standard and later-recurrence/classification quote groups recovered. |

The three full-support questions contribute 3, and three half-support AND questions contribute 1.5, giving literal total support 4.5 across nine answerable questions. The two zero-coverage single-passage questions still recover one required quotation each, so an 8/9 Hit rate and 0.75 MRR obscure substantial incomplete support. All quotations for a required passage remain necessary; partial groups and scoring context receive no complete-support credit. These failures concern the frozen required quote groups, not a claim that candidates contain no related measured facts.

For the three source-grounded no-answer questions, all five candidates are nonempty and none of the six declared own-anchor limitation/context quotes is covered. For the external-validation question, a predeclared passage about a previous external study ranks first; it is not validation of the requested current recurrence model. Other identified hard negatives remain visible in answerable queries: the different sensitivity-analysis table ranks fifth for s1, and training-set performance ranks fourth for e1. These source/analysis distinctions are reported without changing any label or support alternative after ranking.

The prospective fresh gate fails both quality conditions despite intact source integrity and a successful development gate. Development improvement therefore does not establish document-disjoint generalization. The optional candidate remains structurally inspectable, while medical retrieval quality is unaccepted. No later sweep, alternate-method held-out comparison, quote shortening, alternative promotion, parameter change or rerank was performed. The coordinator acknowledged the failed result and directed release of the accepted core ledger and operational candidate interfaces with explicit experimental/failed-quality status; it did not accept medical quality. Root completed code/artifact review and the clean staged regression recorded below. No further algorithm/source ticket is part of this release.

Evaluation recomputed both stored v2 aggregate dictionaries from every per-question row without ranking. All four versioned v1/v2 result byte lengths and hashes remain unchanged. The v2 software suite is frozen at 55 independent cases; the last focused command recorded above passed 119 combined v2/v1 cases. No broad/shared full suite was run; the coordinator owns the final clean staged regression.

## Prepared evaluation controls

The new harness reuses the frozen v1 own-anchor OR/AND and all-required-quote metrics without changing their implementation. It verifies both source/gold checkers and every declared source/gold/code file hash before ranking. Development loads only the original nine questions and old sources, then compares the unchanged BM25 reference and single `bm25_context` candidate. Fresh held-out loads only the new twelve questions and new sources, and executes only the selected eligible method after its receipt binds freeze, development bytes, implementation pins, method parameters and selection rule.

Complete operational traces retain real ledger IDs, original own/context anchors and all source manifests. Own/context anchor counts, per-question support/failure/context/hard-negative rows, repeated and reopened same-ledger traces, and complete before/after SQLite fingerprints are retained. `scoring_context` is reported separately and never credited as finding support. Identical UUIDs across fresh ledgers are not implied. Existing output files cannot be overwritten. Receipt tests are synthetic and run no medical questions.

The fresh held-out prospective gate is nine answerable questions, mean support coverage at least 0.75, at least six complete questions and 100% own/context anchor validity and project/current-source/scope isolation; no-answer rows remain outside the answerable denominator. Development failure must stop before fresh held-out ranking. Default BM25 compatibility is preserved independently of which explicit candidate is selected for evaluation.

Limits: a small document-disjoint, agent-authored pilot can expose retrieval regressions but cannot validate clinical entailment, appraisal, answerability, evidence synthesis or cross-report study retrieval. Known source corrections/discrepancies and non-exhaustive support alternatives remain visible. Context ranking creates no automatic evidence. The earlier v1 held-out quality gate remains failed and unchanged.

## Coordinator release check

Root reviewed the code and independent evaluation evidence, then tested a temporary checkout containing only the staged release files. Both licensed-source verifiers and both frozen question/anchor verifiers passed. With AGNES, NCBI and OpenAI credentials absent and model downloads disabled, the complete suite passed **1,121 tests, five existing PyMuPDF SWIG warnings, in 75.56 seconds**. No medical ranking was rerun. This release accepts the core review workflow and operational passage interfaces; both medical retrieval quality failures remain unaccepted and preserved. Unrelated local benchmark files were excluded from this release rather than subtracted from its test result.
