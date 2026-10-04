# Component retrieval confirmation: original sources

KR4B acquired these two publisher main-article XMLs on 4 October 2026, after the coordinator selected this source split and before any retrieval ranking. This is a new archive. It does not modify previously acquired, graded or frozen fixtures.

| Original article | Title | Attribution | Publication | Canonical blocks / main tables |
| --- | --- | --- | --- | --- |
| [10.1371/journal.pone.0312121](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0312121) | Evaluating diagnostic accuracy and agreement of TI-RADS scoring in thyroid nodules: A comparative analysis between sonographers and radiologists | Abdulrahman M. Alfuraih et al. | 2024-10-11 | 40 / 5 |
| [10.1371/journal.pmed.1004428](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1004428) | Evaluation of hydroxychloroquine or chloroquine for the prevention of COVID-19 (COPCOV): A double-blind, randomised, placebo-controlled trial | William H. K. Schilling et al.; on behalf of the COPCOV Collaborative Group | 2024-09-12 | 60 / 3 |

Both articles grant [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/). The untouched XML includes the complete contributor, copyright and license notices. [manifest.json](manifest.json) additionally preserves ordered individual/collaborative authors, journal, publication date, literal license notice and original publisher provenance. Normalized canonical passages in the sibling truth archive are derived from these originals; the original files are unchanged.

Archive scope is the publisher main article only. Embedded figure/table captions and supplementary-file descriptions remain part of the main XML; linked supplements, figures, underlying patient data and related publications were not downloaded and are not treated as acquired evidence. Reference-list and sub-article passages do not enter the own-block inventory. A trial's own main report is distinct from its reported external-study or meta-analysis context.

Original bytes, exact DOI identity, actual selected article version, attribution/license metadata, complete canonical block inventory and locators are independently reconstructed by [verify.py](verify.py). Existing parser reconciliation occurs afterward in the sibling gold checker. Signed redirect query strings are deliberately omitted; permanent official XML URLs and sanitized version paths remain. Historical parser runtime metadata is retained rather than rewritten when another Python version checks the archive.

The two articles have distinct DOIs from every earlier fixture manifest checked at acquisition and from the other new split. The source-first reading identified separate primary study cohorts/designs/sites/timeframes, with no reused primary cohort across these four articles or earlier fixtures observed. DOI separation alone would not establish cohort independence; this source assessment remains subject to Evaluation's independent acceptance. All observed source inconsistencies relevant to faithful interpretation are recorded as exact path/fragment caveats; no source number or clinical wording has been corrected.

The sibling [truth manifest](../qwen_components_confirmation_gold/manifest.json) binds this source manifest's exact bytes. No model, lexical ranking or paid inference was used to select truth. Integrity checks are structural; independent original-source review must still establish semantic sufficiency and null scope before any run.

```sh
.venv/bin/python tests/fixtures/qwen_components_confirmation_sources/verify.py --self-test
```

The source checker rejects 13 tamper cases and accepts a preserved historical-runtime variant. Paths in the command are relative to the repository root.
'

The coordinator remains blind to confirmation QA before prospective selection; share only hashes, counts, licensing and readiness with the coordinator.
