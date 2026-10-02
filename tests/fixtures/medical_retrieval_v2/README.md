# Fresh document-disjoint retrieval pilot

Status: source/path/anchor reconciliation ready; independent semantic review and coordinator freeze pending. No medical ranking has run against these questions. Candidate/default selection, release to evaluation, and any `freeze.json` are coordinator decisions.

The set has twelve fresh held-out questions, four for each archived publisher source: nine answerable and three source-grounded no-answer requests. Five questions include quantitative estimates, confidence intervals or denominators. Six require an AND combination of two or more passages. Population, allocation/masking, follow-up, matching, exposure/outcome definitions, attrition, reference standards, classification timepoints and negation are also represented. There are twenty-four distinct original XML elements and thirty-one question-specific quote spans. All questions were authored from the articles before any v2 medical ranking, without reading candidate code, v1 held-out questions, or ranks.

The source scope was selected by the coordinator before question authoring. All three own article DOIs are disjoint from the v1 corpus. This folder contains gold and provenance only; publisher bytes remain unchanged in [medical_sources_v2](../medical_sources_v2/README.md). There is no development split here. The frozen v1 development set remains separate.

## Files and interpretation

- `manifest.json` pins exact source bytes and the acquisition manifest, records the split, attribution, correction handling and known printed discrepancies.
- `held-out.json` contains questions, paper-reported answer notes, sufficient support alternatives, exact quote spans, and context-only/hard-negative passage IDs.
- `passages.json` preserves each original XML path, tag, ID, nearest enclosing section title and exact joined `itertext`, alongside canonical paragraph/table text. The `provisional_*` field names are retained for v1 evaluation-schema compatibility; their values have been reconciled with the accepted parser.
- `anchors.json` pins the manifest/question/passage files, complete parser block arrays, parser identity/options/historical runtime, source identifiers, locators, block-text hashes and half-open Unicode code-point quotes.
- `verify.py` first resolves original XML paths and independently checks source/title/license, split membership, support IDs, original text normalization and quote slices. Only afterward does it compare the accepted parser's complete block hashes, locators and quotation bounds. It reads no ranking code, settings, models or index and performs no network calls or ledger writes.

The outer `sufficient_support_sets` list is OR; every passage within one inner list is required (AND). Each passage is covered only if every question-specific quote declared for it is contained in returned **own-block** anchor windows. A question is complete when at least one sufficient set is complete. `scoring_context` is not returned evidence and cannot satisfy a support requirement. Context-only quotations ground no-answer labels or add interpretation; hard negatives can be relevant to the topic while answering a different analysis, population or study. Neither counts as a positive answer. No-answer items have an empty support list and a null expected answer; retrieval must still produce candidates for manual inspection rather than assert answerability.

Every sufficient alternative identified during full canonical abstract/body/table reading is listed, including the secondary-outcome paragraph versus Table 2 alternative. Enumeration remains agent-authored and potentially incomplete; independent semantic review is required before freeze. Figures' image pixels and unacquired supplements were not examined. Some requested values occur in long abstract/table blocks, so a returned window must contain the relevant exact spans rather than merely the same block ID. Multiple passages may be from one article; this corpus establishes no multi-report study linkage.

## Offline verification

From the repository root, with the existing environment:

```sh
.venv/bin/python tests/fixtures/medical_retrieval_v2/verify.py
```

Expected draft result: three pinned sources, twenty-four passages, twelve held-out questions (nine answerable/three no-answer; five quantitative/six AND), thirty-one exact quotes; pilot remains unfrozen. This is a source/anchor check and runs no retrieval. `--fixture-dir` permits a copied fixture directory for read-only tamper checks; its sibling `medical_sources_v2` directory must be preserved because the source paths are relative.

Historical parser runtime metadata stays unchanged. The checker validates the three historical Python version fields as consistent, then compares every other parser option, source pin, complete block array, locator and quote exactly. A different effective Python version alone can pass only when those exact outputs still match; both versions are reported. An inconsistent historical runtime field or changed parser option fails. A coordinator `freeze.json`, when supplied, must declare `status=frozen_before_v2_ranking` and zero medical ranking runs before freeze. Its `held_out.frozen_files` uses full repository-relative paths and must pin all four JSON input/anchor files; any listed local checker/README pins are also validated. It is not authored or altered by Retrieval.

Known internal discrepancies are recorded without silent correction: Singapore abstract rounding versus body/Table 2 precision and the distinct Table 3 sensitivity estimand; Czechia's printed epoch dates/year, serological/laboratory wording and irregular table digit grouping; eNose's printed training recurrence count/percentage. Questions use their declared original element and paper-reported analysis, without computing a correction or treating cited studies as results of the current paper.

## Attribution and version limits

Derived quotations and question notes credit the original authors and sources below. Exact publisher responses are redistributed unchanged under [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/); original license/copyright and complete XML author fields are retained in source and pilot manifests.

- Jafar TH, Tan NC, Shirore RM, Allen JC, Finkelstein EA, Hwang SW, et al., for SingHypertension Study Group (2022), [Integration of a multicomponent intervention for hypertension into primary healthcare services in Singapore—A cluster randomized controlled trial](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1004026), PLOS Medicine, DOI `10.1371/journal.pmed.1004026`.
- Formánek T, Potočár L, Wolfova K, Melicharová H, Mladá K, Wiedemann A, et al. (2024), [Deaths with COVID-19 and from all-causes following first-ever SARS-CoV-2 infection in individuals with preexisting mental disorders: A national cohort study from Czechia](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1004422), PLOS Medicine, DOI `10.1371/journal.pmed.1004422`.
- Schoenaker IJH, van Westreenen HL, Finnema EJ, Schrauwen R, Brohet RM, de Vos tot Nederveen Cappel, WH (2026), [Diagnostic performance of eNose technology in detecting colorectal cancer recurrence: A prospective evaluation](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0340276), PLOS One, DOI `10.1371/journal.pone.0340276`. Author citation uses the publisher's [2 February 2026 correction](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0342238). The notice concerns the sixth author's citation initials and states no clinical-result correction. The coordinator accepted the exact original XML plus notice/corrected citation metadata before authoring; original XML author fields remain unchanged.

All three snapshots were acquired at `2026-10-02T19:48:07Z`. No formal article-version field is present; storage path components are not formal publication versions. No latest/uncorrected status or exhaustive correction/retraction audit is claimed. Clinical numbers were not independently validated. Exact location proves the quoted string belongs to the source; it does not establish clinical truth or whether a manually entered finding is entailed.

This small agent-authored software pilot is not clinical validation, an evidence synthesis, a treatment recommendation, or a validated cross-report study-retrieval benchmark. Source-grounded no-answer requests concern the specific archived article/analysis, not the absence of such evidence elsewhere. Gold and thresholds must be frozen and independently reviewed before any ranking; held-out failures must remain visible and cannot authorize tuning this set.
