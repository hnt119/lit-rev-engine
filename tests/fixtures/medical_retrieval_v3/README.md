# R23 fresh medical retrieval pilot

This directory contains an independently authored, source-first gold pilot for
three accepted original publisher XML snapshots: `cbti`, `ckm`, and `mri`.
Construction used no retrieval rankings, query tests, prior held-out questions
or results, retrieval implementation, external model, or live service. The
coordinator and implementation role remain blind to questions and answers until
prospective selection. Only the source author and fresh Evaluation role review
gold semantics before freeze.

The bounded set has **12 fresh held-out questions**, four per source, with three
answerable and one source-grounded no-answer question per source. There are
**9 answerable, 3 no-answer, 9 actual quantitative, and 8 necessary AND
questions**, supported by **26 distinct original-XML passages and 58 exact
Unicode quote spans**. There are no development questions in this directory.
The quantitative categories require estimates, intervals, or denominators;
semantic review must substantiate them, not merely count their tags.

All identified sufficient alternatives are OR; all members of each alternative
are necessary AND. A question earns necessary-AND credit only if **every**
identified sufficient alternative requires at least two distinct source and
canonical-block identities. Multiple quotes or passage names from one block do
not establish AND. Valid singleton alternatives are retained. The pilot includes
analysis-population, endpoint-definition, adjustment, timepoint, main versus
sensitivity analysis, subgroup, own-cohort versus comparison-study, source-region
precision, nonreporting, and negation distinctions. No-answer labels are scoped
to the included main article and have source-grounded context plus relevant
hard negatives; the unavailable result cannot be supplied by relabelling a
nearby reported estimate.

## Original sources and attribution

- Chen SJ, Que JY, Chan NY, et al. (2025). *Effectiveness of app-based cognitive
  behavioral therapy for insomnia on preventing major depressive disorder in
  youth with insomnia and subclinical depression: A randomized clinical trial.*
  PLOS Medicine. [DOI](https://doi.org/10.1371/journal.pmed.1004510).
- Tsai MK, Kao JTW, Wong CS, et al. (2025). *Cardiovascular–kidney–metabolic
  syndrome and all-cause and cardiovascular mortality: A retrospective cohort
  study.* PLOS Medicine. [DOI](https://doi.org/10.1371/journal.pmed.1004629).
- Bennani-Baiti B, Dietzel M, Baltzer PA (2017). *MRI for the assessment of
  malignancy in BI-RADS 4 mammographic microcalcifications.* PLOS ONE 12(11):
  e0188679. [DOI](https://doi.org/10.1371/journal.pone.0188679).

All three articles use
[Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).
Complete named-author order, publisher, publication date, copyright holder/year,
original license attributes and notices are copied from the XML into
`manifest.json` and independently checked. The original XML license URLs use
`http://creativecommons.org/licenses/by/4.0/`. **No publisher XML was changed.**
This directory's questions, annotations, normalized passage records, verifier,
and documentation were authored for the pilot.

The raw paths are `../medical_sources_v3/cbti.xml`,
`../medical_sources_v3/ckm.xml`, and `../medical_sources_v3_imaging/mri.xml`.
The gold manifest pins both acquisition manifests separately. Only the `cbti`
and `ckm` rows are selected from the legacy manifest; the excluded diagnostic
source is not selected or opened. Existing archives remain acquisition history.
Permanent publisher download URLs, sanitized redirects with signed queries
omitted, original acquisition timestamps, MIME types, sizes and exact SHA-256
hashes are preserved without replacing historical provenance.

The snapshots are not asserted to be latest or free of later corrections.
Storage path numbers are not inferred editorial revision numbers. Publisher
notice observations are limited to the original recorded scope, not an
exhaustive update audit. No external images, supplements, participant files or
other linked assets were acquired or used for gold. The complete main XML
inventory includes its retained title/abstract/body text and reference captions;
it excludes back-matter references and does not inspect linked asset contents.

## Source discrepancies and boundaries

The source manifest retains the acquisition caveats and every relevant original
path/literal fragment. The trial's stated reorganization of the outcome hierarchy
remains a reporting caveat. An additional original-XML observation records the
different signs of the first depressive-symptom interval bound at post-session
4 in the trial's Results versus Table 2; both regions are preserved without
reconciliation. The cohort's baseline-measurement limitation is retained with
its reported repeated-examination time-dependent sensitivity analysis.

The imaging source retains all four R22 observations: the invasive-carcinoma
specificity estimate/interval mismatch; abstract versus Results false-negative
BI-RADS listings; Fisher versus Chi-square test descriptions; and Table 3's own
study year versus electronic publication metadata. Gold keeps source-region
qualifiers and the original reported precision, separates comparison-study rows
from the source cohort, and applies no clinical or numerical correction.

These are source observations, not independent clinical validation or
risk-of-bias judgments. Gold is source-agent authored and independently reviewed,
not clinician adjudicated. A 12-question, three-source nonexhaustive pilot does
not establish general biomedical accuracy or current clinical guidance.

## Files and offline checks

- `manifest.json`: two acquisition-manifest pins, three original-source records,
  preserved provenance/notices/caveats, split membership and fixed count rules.
- `passages.json`: exact joined XML character data, independently normalized
  canonical text, original element paths, source identities and support/context
  passages.
- `held-out.json`: fresh questions, as-reported expected answers or nulls, OR/AND
  sufficient sets, context and hard negatives, and exact quote bounds.
- `anchors.json`: historical parser runtime metadata, source/full-block hashes,
  every selected block's ID/path/locator/ordinal/text hash, draft-file pins, and
  every exact quote anchor.
- `verify.py`: original-XML-first verification and accepted-parser reconciliation
  after independent source/path/text/quote checks.
- `freeze.json`: coordinator-only declaration, intentionally absent until
  independent semantic acceptance and prospective freeze. The source author
  does not write this file in the actual archive.

From the repository root:

```sh
python3 tests/fixtures/medical_retrieval_v3/verify.py --self-test
```

The verifier reads local files and uses the Python standard library plus the
accepted public JATS parser. It imports no retrieval/ranking code and performs
no query, ranking, index, model, network, installation or production operation.
It first checks raw bytes against gold pins **and the unchanged acquisition
rows**, DOI disjointness against all six prior pilot sources, direct XML
metadata/authors/date/license/notices, selected paths, exact joined text,
independent canonical normalization, split/answerability structure and Unicode
code-point quote slices. All **156 original canonical blocks** are independently
enumerated and reconciled in full with the accepted parser: 59 for `cbti`, 69 for
`ckm`, and 28 for `mri`, including 2, 4 and 3 main tables respectively. Full-block
array digests use sorted-key compact finite UTF-8 JSON, `ensure_ascii=False`;
individual text hashes use exact canonical UTF-8 text without extra normalization.

Historical anchors capture Python `3.12.7`. Replay permits only a consistent
Python-version delta, reports the historical and effective versions separately,
and preserves the recorded anchors. All other parser options and provenance
must match exactly. Once the coordinator writes a freeze, all six gold-file
pins are checked; this verifier never rewrites historical anchors or the actual
freeze. Structural quote/path checks do not prove semantic sufficiency or absence
of alternatives. Fresh Evaluation reviews those questions separately before
freeze, and no automatic abstention rate is inferred from context quote counts.

The guarded self-test uses disposable copied fixtures with only selected raw
XML files. It rejects 18 negative cases covering span/Unicode corruption,
source binding and hashes, absent locators, canonical text, block ordinal/text
hash/full-array hash, omitted OR support, a singleton added to declared AND,
duplicate names for one canonical block, relabelled null support, inconsistent
historical runtime, changed parser options, changed acquisition-manifest pins,
changed original raw bytes with rewritten gold/anchor hashes but unchanged
acquisition, and a README modified after a simulated copied-fixture freeze.
A positive runtime case confirms that a consistent historical Python delta is
reported without rewriting anchors. No test mutates an actual source archive,
gold file, historical anchor or coordinator freeze.
