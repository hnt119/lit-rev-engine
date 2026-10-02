# Licensed publisher medical source snapshots

These three peer-reviewed research articles form a small mixed-topic software pilot for later medical retrieval evaluation. They do not constitute a representative benchmark, extraction gold set, systematic review, or clinical validation. No questions, answers, model outputs, participant-level datasets, PDFs, or images were acquired in this ticket.

| Alias/file | Publisher attribution | Publication date | DOI | Exact bytes |
| --- | --- | --- | --- | --- |
| `coach.xml` | Chen et al., PLOS Medicine: integrated depression/hypertension care cluster trial | 2022-10-24 | [10.1371/journal.pmed.1004019](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1004019) | 175830 |
| `whitehall.xml` | Sabia et al., PLOS Medicine: sleep and multimorbidity in Whitehall II | 2022-10-18 | [10.1371/journal.pmed.1004109](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1004109) | 209909 |
| `raptor.xml` | Fanshawe et al., PLOS One: RAPTOR-C19 diagnostic accuracy | 2025-08-07 | [10.1371/journal.pone.0329611](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0329611) | 117858 |

Each article's own XML permissions identify **Creative Commons Attribution 4.0 International** and the original copyright holder: 2022 Chen et al., 2022 Sabia et al., and 2025 Fanshawe et al. The XML retains its original `http://creativecommons.org/licenses/by/4.0/` link; the [canonical CC BY 4.0 license](https://creativecommons.org/licenses/by/4.0/) describes reuse with attribution and marking of changes. `manifest.json` preserves complete author/title/publisher attribution, copyright fields, license attributes/text, publication metadata, and source links. Future derivatives must retain attribution and identify their transformations.

The `.xml` files are **exact HTTP response body bytes** from the publisher's article-page XML download links. There was no rewriting, stripping, normalization, or extraction. Acquisition completed at **2026-10-02T17:54:51Z** for all three files. Permanent download URLs are:

- [COACH publisher XML](https://journals.plos.org/plosmedicine/article/file?id=10.1371%2Fjournal.pmed.1004019&type=manuscript)
- [Whitehall II publisher XML](https://journals.plos.org/plosmedicine/article/file?id=10.1371%2Fjournal.pmed.1004109&type=manuscript)
- [RAPTOR-C19 publisher XML](https://journals.plos.org/plosone/article/file?id=10.1371%2Fjournal.pone.0329611&type=manuscript)

PLOS redirected these requests to its public Google Storage corpus. The manifest retains redirect scheme/host/path, while omitting ephemeral signed query parameters (`final_url_query_omitted=true`); reacquisition should use the permanent publisher download link. A fresh download may differ, so do not silently replace a pinned source. SHA-256 and byte length freeze the acquired snapshot.

These are publisher-delivered full-article JATS XML snapshots of the published articles. The XML has no explicit `article-version` element. Storage path segments `/2/` for COACH and `/1/` for the others are recorded as delivery paths, without inferring formal publication versions. Acquisition time/hash does not establish latest or uncorrected status, and no comprehensive Crossmark/correction/retraction audit was performed. Publisher update notices must be checked before claiming that a later research synthesis uses current versions.

COACH/Whitehall XML declare JATS publishing DTD 1.1d3; RAPTOR declares 1.3. The files contain full article text, table markup, references, and links to figures/supporting material. Linked assets and datasets were not downloaded. Table/paragraph locators are XML locators, not PDF page numbers. References may cite other articles; only `front/article-meta/article-id[@pub-id-type='doi']` identifies each source's own DOI. These full-article JATS files are not PubMed bibliography XML and cannot be passed to the review citation importer as though they were PubMed records.

Run the standalone checker with the existing Python environment; it makes no network calls or operational model/index imports:

```sh
python tests/fixtures/medical_sources/verify.py
```

It verifies all three source hashes/lengths, own DOI/title/authors/license/copyright/publication metadata, full article bodies, and pinned acquisition/version facts. It rejects entity declarations before parsing and ignores external DTD declarations without fetching them. It does not run DTD validation or establish publisher signatures, clinical accuracy, methodological quality, or absence of updates. The exact original bytes remain unchanged. The script is fixture validation, not an operational source extraction interface.

SHA-256 values:

```text
coach     10ae6c2d3371b149a4b6dfa3724f0be6f3b2c49f3f2881e749602fcf50ffcdfb
whitehall 433f2e08e6fb51e9e9d393c3eca21595578741f2fd21d6f4583f918ce99c7ae7
raptor    602572ed2dd22844a2a70830b683c8a85f8891506293003c89df431b2588dc1b
```
