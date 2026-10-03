# Fresh Qwen pilot source snapshots

Ticket R-Q2 acquired two unchanged public PLOS main-article XML snapshots on 2026-10-03, before any Qwen pilot quality ranking. This is a bounded, agent-curated source set for prospective retrieval acceptance, not clinical validation or an exhaustive/latest review.

| Archive | Attribution | Published | SHA-256 | Bytes | Canonical blocks / main tables |
| --- | --- | --- | --- | --- | --- |
| `mammography.xml` | Marlina Tanty Ramli Hamid, Nazimah Ab Mumin, Shamsiah Abdul Hamid, Natasha Mohd Ariffin, Khariah Mat Nor, Ernisha Saib, Nurul Amira Mohamed. [Comparative analysis of diagnostic performance in mammography: A reader study on the impact of AI assistance](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0322925). DOI `10.1371/journal.pone.0322925`. | 2025-05-07 | `18537d74837fde29e423aa014274aa877580130eb3eefa284d35255cdda81385` | 127709 | 55 / 5 |
| `breast_us.xml` | Mingnan Lin and Size Wu. [Ultrasound classification of non-mass breast lesions following BI-RADS presents high positive predictive value](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0278299). DOI `10.1371/journal.pone.0278299`. | 2022-11-30 | `3fa5a7c38a0517fda006c5b32c9f2b51ee09ff1e744453df3e876a21046bd58e` | 108204 | 47 / 4 |

Both own XML notices grant [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Copyright is © 2025 Ramli Hamid et al and © 2022 Lin, Wu, respectively. `manifest.json` preserves the complete original notices, ordered author names, publication metadata, publisher article/permanent XML URLs, exact byte hashes/lengths, acquisition UTC, and sanitized final redirects. Both redirects expose a publisher GCS version path `/1/`; signed query strings are omitted. This observation is a snapshot version description, not a guarantee that the permanent URL can never change.

Original XML bytes are unchanged. Parser block text is a declared derivative: paragraph whitespace collapses, table rows use tabs/newlines, and Unicode characters remain intact. The original paths, locators, ordinals, whole-block digests and historical parser/runtime metadata are recorded. Canonical blocks include title/abstract and body paragraphs/tables, including caption text present in the main XML; reference-list text is excluded. No image pixels, supplements, external datasets, patient-level downloads, private data, credentials or inference were acquired.

The DOI exclusion audit read only the existing `medical_sources*/manifest.json` metadata and compared candidate DOI identifiers, without using old gold/questions or legacy raw XML. `manifest.json` stores those four manifest pins and a zero-overlap result. New source curation and truth remain independent of model results.

Ten source caveats preserve literal regions and canonical fragments. They include mammography improvement/highest-reader claims that disagree with printed values, dense-breast denominators and follow-up wording, an unexplained table dagger column, ultrasound Table 3's unreconciled malignant-column total/parentheticals, a benign-feature count discrepancy, size-measurement wording, and unlabeled interval confidence level. The archive makes no numerical or clinical correction. Publisher notice observation was limited to the article pages, their license links, and own XML; it was not an exhaustive correction/retraction search. The article license does not establish external data/image/supplement licenses.

Run offline:

```sh
python3 tests/fixtures/qwen_pilot_sources/verify.py --self-test
```

The independent checker starts from the exact pinned original bytes and own metadata, reconstructs all 102 canonical blocks/nine tables, and verifies every stored caveat path/fragment. It rejects 13 source tamper cases and accepts one historical-runtime positive case. Tests copy only these two fresh XML files into a temporary directory. The source checker does not query a model, rank passages, open a database, or read old QA. Root owns final prospective freeze pins and quality execution.

Final archive files are `mammography.xml`, `breast_us.xml`, `manifest.json`, `verify.py`, and this README.
