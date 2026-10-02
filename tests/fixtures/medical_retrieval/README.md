# Frozen medical retrieval pilot: 18 questions

Status: **source semantics and anchors accepted; methods/metrics frozen before ranking; evaluation results pending**. Evaluation independently reviewed all 18 question meanings, 23 source passages and 43 exact quotes without finding a source-fact defect. The coordinator's `freeze.json` pins the original draft/anchor files and prospective selection/acceptance criteria. Historical draft labels in those pinned files describe their preparation state; the freeze declaration is authoritative. R11b used `parse_source_bytes` only to reconcile source representations after independently checking original XML paths, text, quotes, and split/support membership. No model, index, network request, ranking run, or existing benchmark change was used to select gold or thresholds.

The questions use only the three exact [licensed publisher snapshots](../medical_sources/README.md): Chen et al. (COACH), Sabia et al. (Whitehall II), and Fanshawe et al. (RAPTOR-C19). All are CC BY 4.0. `manifest.json` preserves complete authors, title, DOI, publication source link, copyright, license, source hash/size, and acquisition time. Source XML was not changed. Passage selection, provisional text normalization, question drafting, and structured answer notes are transformations; quoted source text remains attributed to the original authors. These are paper-reported facts and limits, not clinical recommendations or independently established clinical truth.

Files:

- `manifest.json`: draft status, source/version attribution, explicit split membership/rationale, support semantics, and limitations.
- `development.json`: nine development questions with reported answer notes or explicit no-answer rationale.
- `held-out.json`: nine preassigned held-out questions; do not tune retrieval against their results.
- `passages.json`: 23 exact source element/path/text records, with provisional canonical block IDs/text.
- `anchors.json`: reconciled source/full-block hashes, parser provenance, exact passage block IDs/locators/text hashes, and 43 question-specific anchors. It also pins the unchanged four draft JSON files by byte hash.
- `verify.py`: read-only offline original-source and accepted-parser reconciliation checker.
- `freeze.json`: coordinator acceptance, five file byte pins, fixed candidate parameters, development selection and held-out acceptance thresholds. The checker also verifies these byte pins.

The split was assigned **before retrieval changes or results**. Each split has three questions per article, seven answerable questions, and two no-answer questions. Question targets differ between development and held out. Both splits share the same articles and sometimes passages; this is a question-level holdout, not document-level generalization or a blind clinical benchmark. Reassigning questions after seeing performance would require a new documented evaluation version.

Candidate eligibility requires mean support coverage at five of at least 0.75 and complete support for at least four of seven answerable questions. Select the default on development using coverage, complete-question count and reciprocal rank, with a BM25 tie preference; assess that selected default against the same held-out thresholds. All anchors and operational project/version/scope isolation must be valid. No-answer candidate behavior is reported separately because lexical relevance does not establish answerability. See the [frozen operational/metric contract](../../../docs/project-retrieval-milestone.md).

| Development ID | Target |
| --- | --- |
| `dev-coach-01` | Participant age/diagnosis/depression-screening thresholds; scoped eligibility fields. |
| `dev-coach-02` | Twelve-month arm-specific attrition/deaths and denominators, without double-counting categories. |
| `dev-coach-03` | **No answer:** measured participant medication-adherence percentage; distinguish absent measurement from team activity logs. |
| `dev-whitehall-01` | Multimorbidity definition and excluded risk factors. |
| `dev-whitehall-02` | Age-50 short-sleep HR/interval, reference category, and adjustment context. |
| `dev-whitehall-03` | Different age-specific cohorts and mean follow-up durations. |
| `dev-raptor-01` | Recruited versus complete-case denominators and missing-data exclusions. |
| `dev-raptor-02` | Measured SARS-CoV-2 sensitivity/specificity and uncertainty; manufacturer statements are hard negatives. |
| `dev-raptor-03` | **No answer:** later symptom-resolution rate when participant follow-up was not collected. |

| Held-out ID | Target |
| --- | --- |
| `held-coach-01` | Actual versus originally planned randomization unit. |
| `held-coach-02` | Twelve-month observed control percentages plus endpoint definition; requires two passages. |
| `held-coach-03` | **No answer:** isolated causal Aging Worker-only effect, distinct from the combined intervention effect. |
| `held-whitehall-01` | Disease-free sensitivity-analysis long-sleep result and qualified lack of statistical significance. |
| `held-whitehall-02` | Mortality findings differ across multistate and post hoc analyses; requires both passages. |
| `held-whitehall-03` | **No answer:** randomized causal sleep-intervention benefit cannot be obtained from observational HRs. |
| `held-raptor-01` | Eligibility plus primary-sample age/symptom-duration characteristics; requires two passages. |
| `held-raptor-02` | Planned follow-up/serology were omitted after protocol amendments; do not invent amendment reasons. |
| `held-raptor-03` | Measured influenza B accuracy, intervals, and small positive-case denominator. |

Each question declares its article, challenge tags, answerability, paper-reported answer notes, and relevance/support requirements. `sufficient_support_sets` is an OR of alternatives, each containing an AND of necessary passages. For example, a quantitative diagnostic question can use its complete results paragraph or the matching labeled table; a multi-passage question needs every passage in its selected set. Returning related background alone is insufficient.

`context_only_passage_ids` supplies scope or omission evidence without answering an unsupported requested result. `hard_negative_passage_ids` identifies plausible related text that does not support that question: manufacturer claims instead of measured accuracy, team activity instead of patient adherence, baseline symptoms instead of follow-up, combined intervention effects instead of a component effect, or observational HRs instead of randomized effects. These are proposed relevance judgments, awaiting independent review and coordinator metric/interface decisions.

No-answer questions have null reported answer and no sufficient positive support set. Their cited context supports a grounded abstention, not a fabricated zero/value. Absence is scoped to this frozen three-paper corpus. It does not mean that the broader medical literature contains no answer.

Every passage stores the main article alias/source hash, exact structural path/tag/element ID, nearest section title, and exact concatenated XML text before whitespace normalization. Paragraph text concatenates inline content then collapses whitespace. Tables retain label/caption/tab-separated rows/foot and do not infer spanning-cell semantics. Block IDs are `xml:` plus their paths; the 43 spans use half-open Unicode code-point offsets into canonical block text. The draft JSON files retain their original provisional field names and status. `anchors.json` records their exact agreement with the accepted parser without changing question meanings, split membership, expected values, or support-set truth. XML locators remain element paths; offsets are character positions within canonical block text.

Run from the repository root:

```sh
.venv/bin/python tests/fixtures/medical_retrieval/verify.py
```

The checker first verifies all three pinned source byte hashes/DOIs, resolves each declared path directly in the original XML, reconstructs paragraph/table text independently, and checks every exact quote slice plus question/split/support membership. Only after these checks does it call the public parser on the same captured bytes and compare full block hashes, selected block text/locators, and question anchors. It makes no ledger writes. `--fixture-dir PATH` can check a copied fixture tree that retains the sibling `medical_sources` directory.

Reconciliation captured `lit-rev-engine.source.v1.jats_xml`, historical Python 3.12.7, `normalization=xml-whitespace-v1`, `tables=rows-tab-separated-v1`, `external_dtd=ignored`, and `entities=rejected`. The complete parser arrays contain 79 COACH, 88 Whitehall, and 48 RAPTOR blocks. Their compact sorted-key finite UTF-8 JSON hashes and each selected block's exact UTF-8 text hash are recorded in `anchors.json`. The three historical Python-version fields must be valid and consistent. The checker preserves those fields, separately reports the effective current Python version, and can pass on another supported interpreter when all source/block/locator/quote pins and every other parser option still match exactly. Inconsistent historical runtime metadata or any representation/source/draft-file/parser-option change fails verification. The checker never rewrites historical provenance, questions, or pins to make a mismatch pass.

Only main-article front abstracts/direct body supply finding support. Reference lists and RAPTOR's peer-review `sub-article` bodies are excluded. The study corpus has no established multiple-report study relationship, so the multi-passage questions combine necessary passages within one article rather than asserting a multi-report linkage.

Limitations remain explicit: three selected papers, manual question/support authorship, source/passages shared between splits, unfrozen semantic judgments, and incomplete update/correction auditing. Exact source/block/quote agreement proves quotation location. Independent Evaluation should inspect every answer/context/quotation against the pinned bytes and challenge no-answer scope before coordinator freeze. Retrieval/ranking/support-coverage metrics and acceptance thresholds remain coordinator decisions. No performance or clinical-validation claim is made here.
