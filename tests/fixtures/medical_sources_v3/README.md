# Prospective v3 medical source snapshots

These three primary medical articles were selected and downloaded before any
new questions or retrieval ranking. Source acquisition is complete; coordinator
approval is required before gold authoring. No questions, labels, rankings,
clinical recommendations, participant-level datasets, supplements, PDFs, or
images are included here.

| Alias / exact XML | Design selected from the article | Publication date | Main tables | Own DOI |
|---|---|---|---:|---|
| `cbti` / `cbti.xml` | Randomized clinical trial | 2025-01-21 | 2 | `10.1371/journal.pmed.1004510` |
| `ckm` / `ckm.xml` | Retrospective observational cohort | 2025-06-26 | 4 | `10.1371/journal.pmed.1004629` |
| `truenat` / `truenat.xml` | Prospective cross-sectional diagnostic accuracy | 2025-12-22 | 4 | `10.1371/journal.pone.0327936` |

All three own DOIs are disjoint from the six v1/v2 source DOIs listed in
`manifest.json`. Selection used the frozen design, numerical-results,
inspectable-main-table and CC BY criteria. It used no scientific-performance
judgment, new question content, retrieval score, or observed ranking result.

## Attribution and primary links

- Chen, Si-Jing, et al. (2025). **Effectiveness of app-based cognitive behavioral
  therapy for insomnia on preventing major depressive disorder in youth with
  insomnia and subclinical depression: A randomized clinical trial.** *PLOS
  Medicine*. Copyright © 2025 Chen et al.
  [Publisher article](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1004510),
  [publisher full-article XML](https://journals.plos.org/plosmedicine/article/file?id=10.1371%2Fjournal.pmed.1004510&type=manuscript).
- Tsai, Min-Kuang, et al. (2025). **Cardiovascular–kidney–metabolic syndrome and
  all-cause and cardiovascular mortality: A retrospective cohort study.** *PLOS
  Medicine*. Copyright © 2025 Tsai et al.
  [Publisher article](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1004629),
  [publisher full-article XML](https://journals.plos.org/plosmedicine/article/file?id=10.1371%2Fjournal.pmed.1004629&type=manuscript).
- Mallya, Sarapia P., et al. (2025). **Diagnostic accuracy of the TrueNat™ MTB
  plus assay for detecting pulmonary tuberculosis in adults.** *PLOS One*.
  Copyright © 2025 Mallya et al.
  [Publisher article](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0327936),
  [publisher full-article XML](https://journals.plos.org/plosone/article/file?id=10.1371%2Fjournal.pone.0327936&type=manuscript).

All three publisher pages link to the
[Creative Commons Attribution 4.0 International license](https://creativecommons.org/licenses/by/4.0/);
their own JATS permissions independently identify that same license. Complete
ordered author names, copyright holders, own article title/DOI/date, publication
date attributes, license text and license attributes are retained in the
manifest and original XML. These XML files are redistributed unchanged, with
attribution; the fixture manifest, verifier and this documentation were created
for this repository.

## Exact snapshots and version limits

The verified HTTPS responses were captured at `2026-10-02T20:38:05Z`,
`2026-10-02T20:38:07Z`, and `2026-10-02T20:38:08Z` for `cbti`, `ckm`, and
`truenat`, respectively. Each file's exact byte length and SHA-256 are recorded
in `manifest.json`; no XML reserialization, normalization, numerical correction,
or source replacement was performed.

The permanent publisher XML link remains the replay source. The final publisher
storage redirect retains its scheme, host and path; ephemeral signed query
parameters were deliberately omitted rather than committed. Byte hashes pin
the acquired response. A later network response need not match this snapshot.

None of these own article metadata sections supplies an `article-version`
element. Numeric storage-path segments are not interpreted as formal versions.
During acquisition, no correction/retraction banner or notice was observed on
the primary pages or in targeted publisher-domain DOI searches. This is a
limited observation, not a comprehensive update audit, latest-version claim,
or assurance that the articles are uncorrected. External DTD links and asset
references remain in the unchanged XML; verification does not fetch them.

## Source caveats preserved before questions

- `cbti`: authors explicitly describe multiple protocol primary outcomes without
  a defined hierarchy, and reorganization of that hierarchy when reporting.
  This reporting statement is preserved without an independent appraisal.
- `ckm`: the discussion describes baseline-measurement limitations and also a
  repeated-examination subset with a time-dependent analysis. Both statements
  are retained; the baseline limitation does not mean that the article reports
  no longitudinal sensitivity analysis.
- `truenat`: the abstract assigns sensitivity/specificity **98.9%/95.3% to
  culture** and **86.2%/95.2% to Ultra**. The diagnostic-results paragraph and
  Table 2 assign those pairs to **Ultra** and **culture**, respectively. This
  internal discrepancy is retained without silently selecting a corrected
  reference-test label. Table 2 also retains its supplied contingency counts
  and stated metrics: its Ultra-positive row contains 89 TrueNat-positive,
  8 TrueNat-negative and 97 total, while sensitivity is labeled 98.9. These are
  literal source observations, not a recalculated clinical correction or an
  exhaustive consistency audit.

The manifest identifies the original XML paths and literal fragments for these
observations. The offline verifier resolves them directly in the original XML.
These caveats are source provenance, not a gold question set or evidence that
any clinical conclusion is correct.

Two initially inspected alternatives were excluded **before downloads,
questions or ranking**. The Taenia diagnostic article
([DOI 10.1371/journal.pntd.0012310](https://journals.plos.org/plosntds/article?id=10.1371/journal.pntd.0012310))
uses CC0 rather than the frozen CC BY criterion. The SARS-CoV-2 comparative
diagnostic article
([DOI 10.1371/journal.pone.0282150](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0282150))
had no inspectable main-article table observed on its primary page. Neither
exclusion reflects scientific performance or a retrieval result.

## Offline verification

From the repository root:

```sh
.venv/bin/python tests/fixtures/medical_sources_v3/verify.py
.venv/bin/python tests/fixtures/medical_sources_v3/verify.py --self-test
```

The standard-library-only checker verifies all three raw hashes/sizes, unique
and disjoint own DOIs, own titles/ordered authors/publication dates/copyright,
CC BY 4.0 permissions, permanent download identity, sanitized redirect
provenance, full main bodies, inspectable main tables and retained caveat
fragments. It parses the original XML directly, without an operational parser,
settings, indexes, models, ledgers or network access. It rejects declared
entities and HTML; ElementTree does not fetch an external DTD.

The self-test passed all **14 tamper cases** in temporary copies: changed bytes;
wrong DOI, title, author, license or publication date after deliberately updating
the copy's hash; HTML; declared entities; absent main tables; signed redirect
parameters; wrong download article; omitted or invented caveat fragments; and
duplicated sources. Original fixture bytes are never changed by those tests.
Verification confirms snapshot integrity and metadata consistency, not clinical
validity, comprehensive correction coverage or future retrieval quality.

Coordinator accepted these exact source bytes and metadata before gold authoring, after independently checking original publisher pages, hashes/DOIs/licenses and accepted canonical structure (59/69/36 blocks), and running all fourteen tamper cases. The approval in [the v3 contract](../../../docs/project-retrieval-v3-milestone.md) supersedes the historical acquisition-stage pending wording above and in the manifest. Source/manifest bytes remain unchanged.
