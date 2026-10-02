# R22 imaging source acquisition

This new archive contains one unchanged public publisher XML source. It is a
bounded source acquisition, independent of retrieval rankings and QA. Existing
source archives were not changed. No QA was authored here.

## Attribution and license

Bennani-Baiti B, Dietzel M, Baltzer PA (2017). **MRI for the assessment of
malignancy in BI-RADS 4 mammographic microcalcifications.** PLOS ONE 12(11):
e0188679. [DOI](https://doi.org/10.1371/journal.pone.0188679).

The three named authors in the original XML are Barbara Bennani-Baiti, Matthias
Dietzel, and Pascal A. Baltzer. The publisher is Public Library of Science. The
original XML identifies electronic publication as 2017-11-30 and includes the
copyright holder `Bennani-Baiti et al` and copyright year `2017`.

The article is licensed under
[Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).
The XML's license element and its embedded license link both use the original
`http://creativecommons.org/licenses/by/4.0/` URL. The publisher's copyright and
full license notice remain in the unchanged XML and are transcribed in the
manifest. **Changes to the publisher XML: none.** The manifest, checker, and this
README are archive documentation.

## Provenance and version

- [Publisher article](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0188679)
- [Permanent publisher XML download](https://journals.plos.org/plosone/article/file?id=10.1371/journal.pone.0188679&type=manuscript)
- Retrieved at `2026-10-02T20:58:29Z`; final HTTP status `200`; MIME type
  `application/xml`.
- Original bytes: `76,039`.
- SHA-256: `051c0e8c5e44dd3f7ce85647623d1aed8582fff4dcd2d0a5103b0e9c6cf1a7dd`.
- Sanitized final redirect:
  `https://storage.googleapis.com/plos-corpus-prod/10.1371/journal.pone.0188679/1/pone.0188679.xml`.
  Its signed query parameters were removed from the recorded URL.

The download is UTF-8 XML 1.0 with JATS `dtd-version="1.1d3"`. The returned
storage path component `1` is recorded literally and is not interpreted as an
editorial revision number or evidence of the latest version. Python's local CA
store could not verify the publisher during acquisition; system curl completed
the download with TLS verification enabled. No installation or TLS bypass was
used.

The captured XML has article type `research-article`, no `related-article`
elements, and no `front/article-meta/article-notes` elements. These statements
describe this pinned snapshot; they do not claim an exhaustive or current
correction/retraction search. All original notices and references remain in the
XML. The two figure elements and one supplementary-material element were
retained as references only. No images, supplements, participant-level files,
network models, or other linked assets were acquired.

## Source suitability and table scope

This is a primary retrospective, cross-sectional, single-center clinical breast
imaging study. It includes 248 consecutive patients, routine MRI consensus
reading by two radiologists, and a histopathology reference standard. The
abstract and main Results report TP 103, TN 116, FP 25, and FN 4, with overall
sensitivity 96.3% (reported 95% CI 90.7–99.0%) and specificity 82.3% (75.0–88.2%).
These are source reports, not independently validated clinical findings.

The XML contains three inspectable structured main tables. Table 3,
`pone.0188679.t003`, is **Comparison of MRI performance with published data**.
It has eight columns and five data rows, including an explicitly labelled
`this study` row. Four other rows describe prior studies. The comparison rows
must not be attributed to this article's own cohort. Table 3 gives proportions
rounded to two decimals; the main Results provide percentage estimates with
one decimal. Original precision is retained.

The raw XML contains 14 body section elements, 22 body paragraph elements
(including paragraphs inside captions/footnotes), four abstract paragraph
elements, three main table wrappers, two figure elements, one supplementary
reference, and 35 bibliographic references. These are XML element counts; the
archive does not calculate retrieval block counts.

## Source discrepancies preserved literally

The manifest records the original XML paths and exact character-data fragments
for these four discrepancies. Paths are relative to the root `article` element;
inline tags are removed only when checking character data. No numerical or
clinical correction was applied.

1. In `body//sec[@id='sec014']/p[1]`, invasive-carcinoma specificity appears as
   `72.6% (95%-CI 65.1–69.2%)`. The reported estimate lies outside the reported
   interval.
2. The abstract Results at `front/article-meta/abstract/sec[3]/p[1]` reports four
   false negatives but its parenthetical BI-RADS list includes `2 BI-RADS 4c, 1
   BI-RADS 4b on mammography`. The main Results paragraph in `sec014` additionally
   lists one false-negative DCIS rated BI-RADS 4a. The archive does not reconcile
   these listings.
3. Statistical analysis in `body//sec[@id='sec011']/p[1]` names `Fisher’s exact
   test`; subgroup Results at `body//sec[@id='sec015']/p[4]` names `Chi-square
   test`. Both descriptions are preserved.
4. The Table 3 `this study` row at
   `body//table-wrap[@id='pone.0188679.t003']/alternatives/table/tbody/tr[5]`
   gives year `2016`; the electronic publication metadata gives `2017-11-30`.
   The table year and publication year remain distinct.

## Offline verification

From the repository root, run:

```sh
python3 tests/fixtures/medical_sources_v3_imaging/verify.py --self-test
```

`verify.py` uses Python's standard library and reads only this directory's
manifest and original XML. It does not import project parsing/retrieval code,
fetch a DTD, contact a network service, install anything, or read other source
archives. It checks the frozen original size and SHA-256; direct DOI, title,
author order/names, publisher, publication/citation metadata; complete license
notice/links; table inventories and the inspectable own-study Table 3 row; and
every discrepancy's original XML path and literal fragment. It verifies the
recorded acquisition snapshot and that the final redirect has no query,
fragment, username, or password. It cannot independently prove the historical
HTTP transaction or the authors' clinical findings offline.

The in-memory tamper suite rejects truncated XML, a same-size XML substitution,
changed recorded hashes/sizes/download URLs/timestamps/redirects, changed DOI,
title/date/copyright/license/authors, changed table row counts, a corrected
source fragment, an absent fragment path, a changed XML with a rewritten
recorded hash, and a source path traversal. It never writes tampered content to
the archive. The frozen checker is part of the trusted local record; rewriting
the checker itself is outside this check's integrity claim.
