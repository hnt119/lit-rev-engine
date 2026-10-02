# New licensed publisher source snapshots for v2 preparation

These three newly selected research articles have DOIs disjoint from the v1 corpus. The coordinator selected their source scope before any v2 ranking. This ticket acquires exact publisher full-article XML and provenance only: no questions, gold labels, clinical conclusions, retrieval results, PDFs, images, supplements, or participant-level datasets were acquired. Gold authoring and corpus version handling require separate coordinator acceptance.

The coordinator subsequently accepted all three source pins and approved the exact base snapshots for the software pilot, retaining the known eNose citation correction and its corrected author metadata. The [v2 contract](../../../docs/project-retrieval-v2-milestone.md) records that decision before gold authoring. Pending-decision wording in the original acquisition manifest records the acquisition phase; it does not supersede that acceptance. Original XML and manifest facts remain unchanged.

| Alias/file | Publisher attribution | Publication date | DOI | Exact bytes |
| --- | --- | --- | --- | --- |
| `singhypertension.xml` | Jafar et al. and SingHypertension Study Group, PLOS Medicine: Singapore hypertension cluster trial | 2022-06-13 | [10.1371/journal.pmed.1004026](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1004026) | 216394 |
| `czechia.xml` | Formánek et al., PLOS Medicine: national Czechia cohort | 2024-07-15 | [10.1371/journal.pmed.1004422](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1004422) | 322839 |
| `enose.xml` | Schoenaker et al., PLOS One: prospective eNose evaluation | 2026-01-07 | [10.1371/journal.pone.0340276](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0340276) | 105998 |

Each article's own XML permissions identify **Creative Commons Attribution 4.0 International**. Copyright holders are 2022 Jafar et al., 2024 Formánek et al., and 2026 Schoenaker et al. Complete original author fields, including the collective SingHypertension attribution, title, journal/publisher, copyright, license attributes/text, publication dates, and source URLs are retained in `manifest.json`. The original XML license URLs are `http://creativecommons.org/licenses/by/4.0/`; the [canonical CC BY 4.0 license](https://creativecommons.org/licenses/by/4.0/) describes attribution and identification of changes. Future derivatives must preserve attribution and identify transformations.

The XML files retain **exact HTTP response body bytes**, with no rewriting or normalization. All three acquisitions completed at **2026-10-02T19:48:07Z**. Publisher permanent download links are:

- [SingHypertension full-article XML](https://journals.plos.org/plosmedicine/article/file?id=10.1371%2Fjournal.pmed.1004026&type=manuscript)
- [Czechia full-article XML](https://journals.plos.org/plosmedicine/article/file?id=10.1371%2Fjournal.pmed.1004422&type=manuscript)
- [eNose full-article XML](https://journals.plos.org/plosone/article/file?id=10.1371%2Fjournal.pone.0340276&type=manuscript)

The publisher redirected downloads to its Google Storage corpus. The manifest preserves redirect scheme/host/path but omits ephemeral signed query parameters, with an explicit omission flag/reason. Replay acquisition through the permanent publisher URL. A fresh download may differ; do not silently replace a source pinned by byte length and SHA-256.

These are published full-article JATS snapshots, not PubMed bibliography exports. SingHypertension/Czechia declare DTD 1.1d3; eNose declares 1.3. The XML contains article text, tables, references, and links to other assets. Linked assets and datasets were not downloaded. XML element paths are not PDF page positions, and cited-reference DOIs do not establish the source's own identity.

## Known correction and version limits

The eNose [original publisher page](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0340276) links a [correction published 2026-02-02](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0342238), DOI `10.1371/journal.pone.0342238`. Its stated scope is incorrect sixth-author initials in the article citation. It supplies the corrected citation author form **de Vos tot Nederveen Cappel, WH**. The notice does not describe a clinical-result correction; no comparison against an earlier publisher snapshot was performed.

`observed_publisher_notices` records the primary notice date/URL/scope, corrected citation metadata, and pending coordinator corpus-handling decision. Original base XML author fields remain verbatim; correction XML/assets were not downloaded, merged, or substituted. This records the known update without declaring that the acquired base XML implements it. The source cannot be described as uncorrected or latest.

None of the acquired files has an explicit `article-version` element. Storage segments `/2/` for SingHypertension/Czechia and `/1/` for eNose are delivery paths, not formal publication versions. Acquisition/hash facts do not establish latest status, absence of other updates, methodological quality, or clinical accuracy. Only original-page/known-notice observation occurred; there was no comprehensive Crossmark/correction/retraction audit. Coordinator version handling must precede gold authoring.

## Verify offline

From the repository root using the existing environment:

```sh
.venv/bin/python tests/fixtures/medical_sources_v2/verify.py
```

The read-only standalone checker verifies exact hashes/lengths, own DOI/title/authors/license/copyright/publication fields, full bodies, acquisition/version caveats, and retained eNose correction/citation metadata. It rejects entity declarations before parsing and never fetches external DTDs, imports operational extraction/retrieval code, initializes models, or makes network requests. It performs no DTD validation and authenticates no publisher signature. Source hashes are integrity pins, not clinical validation or proof against consistent external rewriting of source and manifest.

SHA-256:

```text
singhypertension 6e7d1b46497f943ee5b10441ec5cc40d9dc859bea2cda588cf0e77f383466e7e
czechia          5e0516454a0e8435d83783712f3ebcecb0c2317d044f66241269dcb67d3fb27c
enose            19f97daca58580464dde9922bdc5ef52085c7b028d7b516f2284ed688603e9c8
```
