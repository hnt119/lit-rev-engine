# Whole-block retrieval independent evaluation

Status: software, final source-only, fresh gold acceptance and the strict development gate passed. The prospective freeze and selection receipt are fixed. The authorized fresh held-out attempt stopped before any retrieval query on a source-URL schema integration defect; no fresh quality result exists. The v1/v2 failed quality results, frozen truth, parameters and software default remain unchanged.

## Software evidence

The independent gate is `tests/test_project_retrieval_v3_acceptance.py`. It contains 43 cases and uses synthetic sources and the accepted synthetic source fixtures. The receipt-gated harness is `tools/evaluate_medical_retrieval_v3.py`; it reuses the unchanged v1 OR/AND/all-required-own-quote metrics and the accepted independent v2 context validation, then separately checks complete own-block anchors, no duplicate document/block candidates, exact nonblank-block index count and prospective v3 code/gold/parameter pins.

The literal scoring case has two complete representations. Their own lengths are 2 and 401 tokens; the second receives the two-token preceding paragraph once, producing augmented lengths 2 and 403 and average length 202.5. The query token has document frequency 2 and term frequencies 2 and 3. Expected BM25 scores are calculated directly from these integers and the frozen formula, independent of operational token/window/scoring helpers. Duplicate query terms produce the same result.

Exact boundary evidence covers padded TXT with CRLF, composed/decomposed Unicode, emoji and a source BOM, a 401-word TXT block, a 350-word JATS paragraph and a 120-row table retaining its caption, every tab-separated row and table foot. PDF evidence compares complete canonical text and typed physical-page locators against the independent fixture: pages 1 and 3 are indexed, blank page 2 is skipped. A two-page positive query and a one-page positive query distinguish indexed count from matched count. Nonblank stopword-only and punctuation-only blocks remain indexed with no positive matches.

The gate separately verifies every selected manifest field against active same-project documents, current report eligibility, exact source/block hashes and parser provenance; complete own anchors and typed locators; nearest preceding accepted XML paragraph of the same immediate parent with its last 80 exact words; and empty context for TXT/PDF. Context-only table matches cannot satisfy a gold quotation from their preceding paragraph. Four distinct source corruption probes and late canonical PMID enrichment reject selected corrupt/contradictory sources even for a query with no usable tokens.

An instrumented WAL second writer changes both the source version and full-text screening during retrieval. The reader returns the complete original trace from its actual transaction; the next read observes the changed eligibility, and `all_attached` uses only the new active document. API repetition, fresh CLI processes and same-ledger reopening preserve exact trace bytes/values without adding rows. A fresh import/network guard proves the TXT/JATS CLI does not depend on model libraries, settings, dotenv, PDF runtime or live network access. Original token-overlap, BM25 and windowed context methods retain literal scores, parameters, field shapes and 200/40 window boundaries.

The harness cases reject clipped/trimmed full-block anchors, duplicate candidates, wrong index counts, window parameters and missing context. Synthetic development gate cases independently exercise each strict requirement: all 7 complete answers, coverage 1.0, at least one declared no-answer context quote, exact own/context anchors and scope isolation. Synthetic selected-receipt cases reject missing/late authorization, a selected reference method, changed passage unit or window parameters, changed code/freeze/development bytes and a now-ineligible development result. These tests do not rank medical questions.

Commands and observed results:

```text
.venv/bin/python -m pytest tests/test_project_retrieval_v3_acceptance.py -q
initial: 41 passed, 2 failed, 5 existing SWIG warnings, 1.36s

.venv/bin/python -m pytest tests/test_project_retrieval_v3_acceptance.py tests/test_project_retrieval_v2_acceptance.py tests/test_project_retrieval_acceptance.py -q
162 passed, 5 existing SWIG warnings, 3.24s

.venv/bin/python -m pytest tests/test_project_retrieval_v3_acceptance.py -q
final focused: 43 passed, 5 existing SWIG warnings, 0.84s
```

The initial failures were evaluator assumptions, disclosed to the coordinator before correction. The accepted `utf-8-sig` parser strips a leading BOM from canonical text while retaining the exact source bytes; the test had incorrectly included it in the canonical quote. The PDF query `fixture` occurs only on physical page 1, so it should yield one match against two indexed nonblank pages. The corrected test uses the independently printed shared word `physical` for two positive matches, retains the separate one-match assertion, uses the fixture's established `pdf:page:N` block IDs and keeps all exact full-bound/padding/source-byte comparisons. Neither correction changed operational code, source/gold bytes or the whole-block contract.

The E11a evaluator independently replayed the combined 43 new and 119 unchanged retrieval acceptance cases after reviewing the current production method and receipt-gated harness: 162 passed, 5 existing SWIG warnings, 3.24s. This replay executed synthetic/fixture software cases only and did not read or rank held-out medical questions. No production or harness defect was found.

## Prospective medical gate

The historical R20 source acquisition remains unchanged. Its third source is superseded prospectively by R22's separate imaging archive before any question authoring or ranking. The final corpus retains the previously accepted trial and cohort, with 59 and 69 canonical blocks and 2 and 4 tables respectively, and adds the independently accepted imaging source below. The selected corpus therefore contains 156 canonical blocks and 9 tables. The cohort's baseline/repeated-examination distinction remains preserved. The coordinator owns the final source-selection and DOI-disjointness record.

E11a reviewed only the new R22 archive's original XML, manifest, attribution README and offline verifier. The unchanged `mri.xml` is 76,039 bytes, SHA-256 `051c0e8c5e44dd3f7ce85647623d1aed8582fff4dcd2d0a5103b0e9c6cf1a7dd`. Its own DOI is `10.1371/journal.pone.0188679`; the title, ordered authors Barbara Bennani-Baiti / Matthias Dietzel / Pascal A. Baltzer, PLOS ONE publisher metadata, 2017-11-30 electronic publication date and complete original CC BY 4.0 permission notice agree with the manifest and attribution. The R22 manifest is 8,091 bytes, SHA-256 `05d2a7008f0f9bb36eeaf2bdcd6b47b4074c53b53802890ce8ab2c376913bb8b`.

The accepted source parser produces 28 nonblank canonical blocks: 1 article title, 24 paragraphs and 3 complete tables. E11a independently resolved all 28 original XML paths, reconstructed every complete canonical text, and checked unique block IDs and sequential ordinals. The canonical block-list digest is `b18962d56b78f9bb92cbf529ab7704e195f80213d0c73a78f982f9c8b70fb9e6`. All three structured tables retain their original captions, rows and available footnotes. Table 3 has eight columns and five data rows; its four prior-study rows remain distinct from its own-study row. No retrieval query was used for this check.

Original-XML review independently identified and confirmed all four disclosed discrepancies: incomplete abstract false-negative subgroup enumeration relative to the body; an invasive-specificity point estimate outside its printed interval; Fisher's exact test in Methods versus Chi-square in Results; and the own-study Table 3 year 2016 versus electronic publication in 2017. Each manifest evidence path selects its original text, and no source values were corrected. Snapshot notices, storage-path version ambiguity, rounded table precision and references to unacquired figures/supplements remain explicit caveats. Historical HTTP acquisition cannot be reproved offline, and no latest-version or comprehensive correction-audit claim is made.

`.venv/bin/python tests/fixtures/medical_sources_v3_imaging/verify.py --self-test` independently exited 0 and rejected all 18 in-memory tamper cases. These cover changed/truncated XML, rewritten source hash, acquisition identity/time/URL pins, metadata/author/license changes, table row inventory, absent or numerically corrected discrepancy evidence, and path traversal. The verifier reads only its own source archive and imports no project parsing or retrieval code. No source or archive bytes were altered during acceptance, and no fresh QA or ranking was read or authored by E11a.

E11b began with original-XML-first review of the retained trial/cohort and previously reviewed imaging source. Before fresh gold inspection, it independently reconciled all 156 selected canonical blocks to complete original XML text and paths, exact sequential ordinals and unique IDs. The trial and cohort canonical block-list digests are `054e9aeecf101c8b51bdcb8522cc57f893be8a48e99a1e98d93b0c088033bb83` and `10c904f32475dffe4a99383bf6629cacd971364a09da03a7ad431c209f1ee650`. Runtime metadata is Python 3.12.7 with the unchanged `lit-rev-engine.source.v1.jats_xml` parser, `xml-whitespace-v1` normalization, tab-separated table rows, ignored external DTD and rejected entity declarations. No retrieval query was executed.

E11b fresh gold acceptance passed before any freeze or ranking. Original-XML-first semantic review covers all 12 fresh held-out questions, four per selected source, with 3 answerable and 1 source-scoped no-answer per source. All 9 answerable questions genuinely request quantitative estimates, intervals or denominators. Eight questions require multiple distinct source/canonical blocks in every identified sufficient alternative; 16 identified OR alternatives are preserved, including 15 multi-block alternatives and one valid singleton. Distinct passage names or quotes from one block do not establish necessary AND. Each necessary block supplies a requested answer part. The three null labels retain relevant context and hard negatives and are scoped to the included main article; no unavailable estimate is inferred from a nearby reported result or an unacquired linked asset.

Five private semantic/quotation corrections were resolved before acceptance: an omitted sufficient alternative was added; adjustment support was completed; the analysis population became an explicit requested fact; an unrequested metadata explanation was separated from answer evidence; and a required quotation made adjustment scope explicit. These corrections preserved all question-count floors and fixed gates. The coordinator and implementation role received only counts, categories, hashes and defect status, without fresh question/answer content. Evaluation authored no questions and edited no gold, source, production, harness or test files.

Independent direct checks match all 3 gold source metadata copies, 18 top-level identity fields, ordered authors and complete license notices, unchanged raw sizes/hashes and 13 original caveat path/literal observations. All 156 canonical blocks, 26 distinct declared passages and 58 Unicode half-open quote spans reconcile exactly. All recorded source/full-block digests, passage IDs/paths/locators/ordinals/text hashes, quote anchors and 3 draft-file pins match independently computed values. Historical and effective parser runtime are both Python 3.12.7; parser options and captured historical anchors remain unchanged.

`.venv/bin/python tests/fixtures/medical_retrieval_v3/verify.py --self-test` independently exited 0: all 18 negative cases rejected and the consistent historical-runtime-delta positive case passed without rewriting anchors. The strengthened verifier ties raw bytes through gold size/hash pins to unchanged archived acquisition size/hash pins. Its rewritten-gold/source-hash negative rejects against the original acquisition record. Other negatives cover Unicode/span/source/path/block/hash corruption, omitted OR support, singleton AND tampering, duplicate IDs for one block, null relabelling, parser/runtime changes, acquisition pins and an own file changed after a disposable simulated freeze. Temporary test copies contain only selected raw XML and required opaque acquisition records; the excluded raw source is not opened. The actual coordinator freeze remained absent throughout E11b.

The accepted six fresh gold file pins are:

```text
manifest.json   37,329 bytes  75e4671eba59b28a22d40798445d41f52b426c34f3e1964b9f884f707d9b7a3b
passages.json   92,063 bytes  e350b85539d835fe06aac9d660ad3fbcb50665191bf465138a0e31d8656a7296
held-out.json   38,654 bytes  ec80bcba02b8148321e43922181c2544eb981cbab5628c25cb2f8e546bfe280d
anchors.json    49,643 bytes  a9b6e9e00cb9b2f6c1d38f34ec6a19f189baae980fa952dc80112b5860a43e1c
verify.py       36,039 bytes  59e28b663a00be0675bef43e3f172560018ddfdcf0e3d5ec11151c4951a4f658
README.md        9,235 bytes  f285626ae3210a248218c59cbf0817daee937211c2ee020d3ff8b0516c554d92
```

These files are in `tests/fixtures/medical_retrieval_v3/`. The gold remains agent-authored and nonexhaustive; source-grounded support and absence review does not establish clinician adjudication or clinical validity. No medical ranking, retrieval query test or production tuning informed this acceptance.

After the prospective v3 freeze, authorized development may compare only the unchanged `bm25_context` reference and `bm25_context_blocks` candidate on the original 9 development questions. A failing strict gate stops before fresh ranking. Fresh held-out ranking requires a coordinator receipt selecting the eligible candidate and pinning code, parameters, development bytes and the freeze. Its thresholds stay coverage >=0.75 and >=6/9 complete answers with exact anchors and project/active-source/scope isolation. No old held-out ranking is authorized.

Operational traces retain ledger UUIDs and the resulting UUID-bearing manifest hashes. Same-ledger repetition and reopening are exact; independently created ledgers legitimately have different IDs and hashes. Any cross-ledger artifact comparison must compare normalized manifests/anchors/scores/parameters and recompute a normalized comparison digest, while preserving actual recorded hashes.

## Development result (E12)

The coordinator wrote the final prospective freeze at `2026-10-02T21:36:37.342247+00:00`, SHA-256 `90147e3d3e28035a1d3ca1f41a48be36bb2ad6cbc30c08d8df8c0c90945d2070`. E12 then executed the authorized command once:

```text
.venv/bin/python tools/evaluate_medical_retrieval_v3.py --split development --output docs/medical-retrieval-development-v3.json
exit 0; development candidate eligible=true; all eight prospective checks=true
```

The harness verified every prospective source/gold/code/metric/harness/test/contract pin and both source/gold checkers before ranking only the original 9 development questions on their original 3 sources. The result is preserved at `docs/medical-retrieval-development-v3.json`: 493,461 bytes, SHA-256 `ad29db4febf8189838cab14c02abaa834a324dacf9ccd77e6443fdb7695c5f46`. It records `held_out_ranked=false` and `held_out_authorized=false`. No pinned file was edited, no ranking was rerun and no parameter sweep was performed.

| Metric at five | Windowed context reference | Whole-block candidate |
| --- | ---: | ---: |
| Questions / answerable / no-answer | 9 / 7 / 2 | 9 / 7 / 2 |
| Complete answerable questions | 7/7 | 7/7 |
| Complete-question rate | 1.0 | 1.0 |
| Any-required-support hit rate | 1.0 | 1.0 |
| Mean support coverage | 1.0 | 1.0 |
| Mean reciprocal rank | 0.7380952380952381 | 0.7380952380952381 |
| Declared no-answer context quotes recovered | 1/2 | 1/2 |
| No-answer nonempty-candidate rate | 1.0 (2/2) | 1.0 (2/2) |
| Exact own anchors checked / validity | 45 / 1.0 | 45 / 1.0 |
| Exact scoring-context anchors checked / validity | 24 / 1.0 | 23 / 1.0 |
| Project / active-document / scope isolation | 1.0 | 1.0 |
| Indexed passages | 241 | 215 |

Both methods remain read-only and exactly repeatable in the same reopened ledger. Every candidate eligibility check passes: method and denominator, 7 complete answers, mean coverage 1.0, at least one declared null context quote, exact own/context anchors and scope isolation. This grants eligibility for coordinator selection; it does not authorize fresh ranking or establish fresh retrieval quality.

All first-required-quote ranks and every recorded required-quote rank are unchanged between methods; no required-quote rank regression or coverage/completeness regression occurred. Every positive row is complete with coverage 1.0:

| Development question | Reference first required-quote rank | Candidate first required-quote rank |
| --- | ---: | ---: |
| dev-coach-01 | 1 | 1 |
| dev-coach-02 | 3 | 3 |
| dev-whitehall-01 | 1 | 1 |
| dev-whitehall-02 | 1 | 1 |
| dev-whitehall-03 | 3 | 3 |
| dev-raptor-01 | 1 | 1 |
| dev-raptor-02 | 2 | 2 |

`dev-coach-03` is a declared no-answer row: neither method recovers its required context quotation, and both still return five candidates. `dev-raptor-03` is the other no-answer row: both recover its one context quotation in an own anchor at rank 1 and return five candidates. Context recovery is not an automatic abstention or answerability result. The declared `R_manufacturer_claims` hard negative is returned at rank 3 for `dev-raptor-02` by both methods; it remains a misleading alternative to the primary study result. The second declared sufficient table alternative on that row is unrecovered by both methods, while the first alternative is fully covered. No other declared hard-negative hit or failure-mode annotation is reported by the frozen metrics.

For completeness, the first position of an arbitrary canonical block within the observed top five can regress even while required-quote metrics are unchanged. Matching by document and canonical block, the five observed regressions are:

| Development question | Source / canonical XML path | Reference first block rank | Candidate first block rank |
| --- | --- | ---: | ---: |
| dev-coach-03 | coach: `/article[1]/body[1]/sec[3]/p[3]` | 3 | 4 |
| dev-coach-03 | coach: `/article[1]/body[1]/sec[3]/table-wrap[2]` | 4 | Outside top five |
| dev-whitehall-02 | whitehall: `/article[1]/body[1]/sec[3]/sec[2]/table-wrap[1]` | 3 | Outside top five |
| dev-whitehall-03 | whitehall: `/article[1]/front[1]/article-meta[1]/abstract[1]/sec[2]/p[2]` | 4 | 5 |
| dev-raptor-03 | raptor: `/article[1]/body[1]/sec[3]/sec[4]/p[1]` | 4 | 5 |

“Outside top five” records only the available trace bound; no additional ranking was run to find its later position. Window and whole-block boundaries differ, so this comparison uses each block's first returned position rather than treating unlike own spans as identical candidates. Fresh gold, parameters, quality thresholds and the candidate remain frozen after observing development.

## Held-out attempt (E13)

The coordinator fixed selection at `2026-10-02T21:42:20.857482+00:00` before inspecting fresh QA or producing a fresh held-out result. `docs/medical-retrieval-selection-v3.json` has SHA-256 `57f4de47eeca2ca339ef5faaad7d3572bba541c935f24085074a44c03a846e52`. E13 attempted the authorized selected-only command once:

```text
.venv/bin/python tools/evaluate_medical_retrieval_v3.py --split held-out --selection docs/medical-retrieval-selection-v3.json --output docs/medical-retrieval-held-out-v3.json
exit 1; KeyError: 'publisher_article_url' at evaluate_medical_retrieval_v3.py:163
```

All freeze and selection checks completed, but the first source attachment failed while reading its URL. The frozen gold source rows preserve publisher URLs inside acquisition records (`publisher_url` for the retained sources, `publisher_article_url` for imaging), while the harness requires a top-level `publisher_article_url`. The failure occurred before the retrieval loop and wrote no held-out result. No fresh query/ranking, overwrite, retry, parameter sweep or frozen file edit occurred. Freeze, selection and development result hashes remain unchanged. This is a demonstrated source-schema/harness integration defect, not a measured fresh retrieval-quality failure. Evaluation reported it to the coordinator; any correction and new authorization belong to the coordinator.

## Metadata adapter acceptance (E14)

The coordinator chose a separate URL-metadata wrapper after E13's setup failure, preserving every original source, gold, contract, harness, production, freeze, development and selection byte. `tools/evaluate_medical_retrieval_v3_schema.py` validates a new coordinator repair receipt before importing the frozen evaluator, invokes only its held-out split, and temporarily replaces only its JSON reader for the exact selected manifest. The reader deep-copies that manifest and adds missing `source.publisher_article_url` fields from its explicit acquisition URLs. It restores the original reader in `finally`, including metadata and evaluator errors. Existing URL spelling and every other source/manifest field remain unchanged. HTTPS PLOS origin, journal path, exact DOI, single `id` parameter and agreement among explicit URLs are required; missing, invalid and conflicting values fail. No URL is fetched or inferred.

E14 independently tested both archived acquisition schemas and existing top-level URLs using synthetic metadata, actual temporary-file byte snapshots, canonical JSON comparison after removing only the two added fields, and deliberate mutations of returned nested data. Unselected manifest reads preserve their original object, including malformed metadata. Every missing or changed freeze/development/selection/adapter/focused-test/independent-test file, bad phase/status, non-boolean failed-attempt marker, wrong input path, malformed/missing/extra repair pin and bad optional independent-test pin rejects before frozen-evaluator import. Synthetic success preserves the original result except the repair-receipt file/SHA fields; synthetic metadata failure restores the original reader. The focused suite also proves a direct-script fresh process works outside its copied synthetic repository with empty `PYTHONPATH`, using a metadata-only evaluator stub, and rejects development and an existing output before evaluation.

The initial independent adapter run had two positive-test failures caused by an incorrectly encoded synthetic URL: the test encoded a hostname slash as well as its intended DOI separator. Correcting only that evaluator fixture resolved both failures. No adapter or frozen implementation change followed the tests. The final commands and outcomes were:

```text
.venv/bin/python -m pytest tests/test_medical_retrieval_schema_adapter.py tests/test_medical_retrieval_schema_adapter_acceptance.py -q
69 passed, 31 subtests passed, 0.29s (14 focused implementation tests and 55 independent acceptance cases)

.venv/bin/python -m pytest tests/test_project_retrieval_v3_acceptance.py tests/test_project_retrieval_v2_acceptance.py tests/test_project_retrieval_acceptance.py -q
162 passed, 5 existing SWIG warnings, 3.22s
```

Read-only adaptation of the actual selected manifest independently adds exactly three missing URL fields. Removing those fields produces canonical JSON identical to the original; the original object and raw manifest bytes remain unchanged. All 33 original frozen pin entries independently match actual bytes, and the earlier freeze, development and selection hashes remain exact. These checks executed no medical query or ranking. E14 found no remaining schema-adapter defect. The new accepted files are:

```text
tools/evaluate_medical_retrieval_v3_schema.py             9,627 bytes  192ea7ff4803d20dca2b389c3042f17ad2b8439d6caa8e5875836111801c882e
tests/test_medical_retrieval_schema_adapter.py           16,678 bytes  3fe47d7d8419ca3a216d8b94408df9fc9d971c4dae8a0b62cbaa303f2d50a113
tests/test_medical_retrieval_schema_adapter_acceptance.py 10,555 bytes  fbb233ca28024c571f34e57c397531b86debf0f8c513424f4e1dfa68eef1f738
```

The coordinator must write the repair receipt with these pins and separately authorize the first actual fresh grade. The adapter adds URL provenance to document attachment metadata; candidate ranking inputs, original guards, metrics, selection and quality thresholds remain unchanged. The prior setup attempt still has zero fresh rankings and no quality outcome.

## Fresh selected result (E13b)

After E14 acceptance, the coordinator fixed `docs/medical-retrieval-v3-schema-repair.json`, SHA-256 `71c3f9c54dc58af371e0818fd97e098ad85b002247b3d332e0355844630525c1`. The receipt pins the accepted adapter and both synthetic test files, the original prospective freeze, the unchanged qualifying development result and the original selected receipt. It declares the earlier attempt unranked and the repair phase before the held-out retry. The coordinator separately authorized the following command once:

```text
.venv/bin/python tools/evaluate_medical_retrieval_v3_schema.py --split held-out --selection docs/medical-retrieval-selection-v3.json --output docs/medical-retrieval-held-out-v3.json
exit 0; selected bm25_context_blocks only; all six fixed fresh acceptance checks=true
```

The first actual fresh grade is preserved at `docs/medical-retrieval-held-out-v3.json`: 400,219 bytes, SHA-256 `c75573df0b81498b1fbb388aad4e8b392a0bb615742693f6fc7d13c21c6f49a3`. It records the exact repair-receipt file and SHA alongside the original freeze and selected-receipt SHA. The wrapper ran the unchanged source/gold checkers, original selection/development validation and original metric/trace guards. No prior result, gold, source, production, contract or harness byte changed. No development rerun, additional method, old held-out run, parameter sweep or quality-driven edit followed the result.

| Metric at five | Fresh selected candidate |
| --- | ---: |
| Questions / answerable / no-answer | 12 / 9 / 3 |
| Complete answerable questions | 6/9 |
| Complete-question rate | 0.6666666666666666 |
| Any-required-support hit rate | 1.0 |
| Mean support coverage | 0.8518518518518519 |
| Mean reciprocal rank | 0.8888888888888888 |
| Declared no-answer context quotes recovered in own anchors | 1/4 |
| No-answer nonempty-candidate rate | 1.0 (3/3) |
| Exact own anchors checked / validity | 60 / 1.0 |
| Exact scoring-context anchors checked / validity | 36 / 1.0 |
| Project / active-document / scope isolation | 1.0 |
| Indexed nonblank canonical blocks | 156 |

The fixed gate passes: 9 answerable questions, mean support coverage at least 0.75, at least 6 complete answers, and 100% own/context anchors and scope isolation. The complete count is exactly the required minimum. The harness verifies read-only retrieval and exact repeated/reopened same-ledger traces; all flags pass. This grade measures the one frozen method on this fresh corpus and does not establish an improvement against another method or prior pilot.

| Fresh question | First required-quote rank | Best sufficient-alternative coverage | Complete |
| --- | ---: | ---: | --- |
| v3-cbti-01 | 1 | 1.0 | Yes |
| v3-cbti-02 | 1 | 2/3 | No |
| v3-cbti-03 | 2 | 1.0 | Yes |
| v3-ckm-01 | 1 | 1/2 | No |
| v3-ckm-02 | 2 | 1/2 | No |
| v3-ckm-03 | 1 | 1.0 | Yes |
| v3-mri-01 | 1 | 1.0 | Yes |
| v3-mri-02 | 1 | 1.0 | Yes |
| v3-mri-03 | 1 | 1.0 | Yes |

The three incomplete positive outcomes remain failures of complete support. `v3-cbti-02` retrieves the remission estimate and analysis but misses the block defining all three remission criteria; its two alternatives cover 1/2 and 2/3. `v3-ckm-01` retrieves the adjusted mortality association but misses the outcome-code definition, and also misses adjustment-analysis support in its body alternative; its three alternatives cover 1/3, 1/2 and 1/2. `v3-ckm-02` retrieves the stage-specific outcome table but misses both alternative stage-definition blocks; each alternative covers 1/2. Their recorded failure mode is `incomplete_sufficient_support_set`, with no partially recovered multi-quote passage. All 9 positives have at least one required own quotation; an early quote hit does not make those three answers complete.

Two complete questions still have unrecovered alternatives: `v3-cbti-03` fully covers its first alternative while its table/discussion alternative covers 1/2, and `v3-mri-01` fully covers its body alternative while its abstract alternative covers 1/2. Completeness correctly uses OR across sufficient alternatives and AND within each alternative. Scoring-context quotations are never credited as own support.

| No-answer question | Declared context quotations recovered in own anchors | Declared hard negative returned | Candidates returned |
| --- | ---: | --- | ---: |
| v3-cbti-04 | 0/2 | Overall trial primary result at rank 2 | 5 |
| v3-ckm-04 | 0/1 | Stage outcome table at rank 1 | 5 |
| v3-mri-04 | 1/1, at rank 1 | None | 5 |

None of the four declared null-context quotations appears in a scoring-context anchor; the one recovered quotation is its own paragraph. The trial null still lacks the requested under-18 estimate despite returning the overall result. The cohort null still lacks the specifically defined stage-1 estimate despite returning the stage table. The imaging null retrieves the limitation that the requested planning outcome was not investigated. All three nulls return candidates, and retrieval creates no abstention or answerability decision. The absence of a declared hard-negative hit on other rows does not rule out undeclared misleading passages.

E13b independently rechecked all 156 complete blocks against original selected XML paths, exact title/paragraph/table text and typed locators, plus all 26 gold passages and 58 Unicode spans. It verified all 60 complete own anchors and all 36 nearest-preceding-paragraph scoring-context anchors, exact last-80-word offsets, source/blocks/parser hashes and metadata, selected document/record ownership, source URLs, version and screening/linkage projections. Every trace manifest hash independently recomputes, all traces select the same three included sources, and every trace indexes 156 blocks. It recomputed every declared quote rank, passage coverage, alternative fraction, completeness flag, reciprocal rank, null-context count, hard-negative hit and aggregate metric from recorded own anchors without calling retrieval or the metric helpers. All recorded row/aggregate/gate values match; the immutable result bytes and all 33 earlier frozen pin entries remain exact.

The coordinator independently recomputed the literal source/own/context/support evidence and accepted this bounded v3 gate. The coordinator's acceptance preserves the three incomplete positives and null hard negatives, and does not claim clinical validity, automatic abstention or improvement across pilots. Final clean staged software regression and release/Git actions remain coordinator-owned. Evaluation stops ranking and tuning after this accepted fresh result.

## Limits

Synthetic software acceptance alone does not establish medical retrieval quality. The accepted prospective pilot remains agent-authored and small; it does not establish clinical validation, exhaustive sufficient-support alternatives or quotation entailment. Whole blocks may be long; they remain inspectable reviewer-facing candidates and do not automatically become findings or model inputs. Context remains ranking provenance only. The retained ledger hashes detect source/block corruption but do not authenticate a consistently rewritten external database.

## Clean release gate

The coordinator exported only staged release files to a new temporary checkout, removed API credentials and disabled model downloads. All four licensed-source archive checkers and all three frozen medical-question checkers passed. The complete suite passed **1,240 tests and 31 subtests in 77.00 seconds**, with five existing PyMuPDF SWIG warnings. This gate did not rerank medical questions or rewrite any frozen artifact. Later documentation edits record this result; original source/gold/code/metric/receipt/result pins remain exact. Authorized GitHub publication remains coordinator-owned.
