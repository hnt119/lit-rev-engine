# Source-anchored evidence: independent evaluation

## E6a source-document API gate

Status: accepted by the coordinator after code and independent evidence review. Evaluation owns `tests/test_review_documents_acceptance.py` and this report. No operational files, clinical gold labels, existing data, environment settings, or concurrent retrieval work were changed. Extraction proposals, verification, appraisal, and command-line interfaces are outside this source ticket.

Retrieval authored the source bytes, locators, canonical text, and quotation truth independently in `tests/fixtures/evidence/manifest.json`. Evaluation verifies those source hashes/lengths, sorted-key compact finite UTF-8 block hashes, and every literal half-open quotation slice before comparing operational results.

| Independent source | Format | Expected blocks | Truth exercised |
| --- | --- | ---: | --- |
| source-v1.txt/source-v2.txt | UTF-8/BOM text | 1 each | Exact CRLF, composed/decomposed Unicode, emoji, and 6→8 weeks source revision |
| article-v1.xml/article-v2.xml | Synthetic JATS XML | 7 each | Title/abstract/body order, nested inline concatenation, structural paths, sections, complete table/foot, reference exclusion |
| three-pages.pdf | Synthetic PDF | 3 | Actual pages 1/2/3, blank page 2, printed labels 10/12 retained as text |

All five source/block hashes and all 16 Unicode code-point quote slices match. XML tables are one block, with caption/foot paragraphs represented once and cells separated by tabs; a spanning cell remains one textual cell. `X<sub>2</sub>` becomes `X2`. XML locators identify elements, not PDF pages. PDF block text is the existing runtime's sorted extraction with no further rewriting. Runtime Python/PyMuPDF versions and all frozen parser options are retained exact metadata; generator provenance is not substituted for the effective runtime.

The 68 independent acceptance cases prove:

- Pure parsers operate on supplied bytes without source-file reads. Attachment parses, hashes, and stores one immutable snapshot even when the original path changes while parsing. Repeated bytes create distinct immutable versions; per-report sequence, active latest version, all older bytes/blocks, and source URL/version labels survive reopening and deletion of the original source file. Stored reads and exports do not reparse documents or initialize the PDF parser.
- Empty/invalid byte inputs, unsupported formats, invalid UTF-8, malformed/error/nonarticle/entity XML, corrupt/encrypted/all-blank PDF, unsafe basenames including control characters, and invalid reviewer/reason/metadata fail with no document or count side effect. Unknown/cross-project report/document/project reads or attachments preserve both projects. Existing screening/retrieval/import/count meanings remain unchanged.
- Source identifiers come only from the primary JATS `front/article-meta/article-id`; DOI/PMID normalize through accepted rules. Equivalent repeated forms are accepted, invalid/conflicting own IDs fail, and cited IDs never supply identity. TXT/PDF and identifier-free JATS retain `{}`. Attaching source identifiers cannot fill bibliography metadata or contradict a known same-type canonical report identifier. A code review also confirms the contradiction check rereads the canonical report inside `BEGIN IMMEDIATE`.
- Namespaced JATS preserves local-tag structural paths and one-based same-tag sibling indices. Reference lists and nested peer-review/editorial `sub-article` branches contribute no primary finding blocks, while source bytes remain exact.
- Tampering with an inactive version's original byte BLOB, canonical blocks, source/block hashes, or stored block JSON makes both public getters and export reject it. Every preexisting export file remains byte-identical and no staging debris remains. This tests inconsistent byte/block tampering; consistent external rewriting of all unsigned SQLite data/hashes is explicitly outside the ledger's guarantee.
- Exports retain all metadata/version-specific blocks/source bytes, exact paths and manifest hashes/lengths, safe formula-like CSV text, nested parser metadata/identifiers, unrelated annotations, and immutable JSON originals. An unchanged snapshot exports identical bytes. A deterministic WAL second writer attaches a new version after the reader captures records; the export retains the complete old metadata, active version, blocks, bytes, and counts while the next read sees the new version.
- Reconstructed old schemas reopen without document data or new count meanings and keep the generic nine-file export. A combined source/PubMed/manual-study export retains all six PubMed assets and the original receipt alongside study arrays and document artifacts. A fresh process parses TXT/JATS and reads/exports durable PDF blocks/bytes without model libraries, settings, dotenv, PDF parser import, or network.

## Actual pinned publisher JATS sources

The three acquired medical sources in `tests/fixtures/medical_sources/` are actual licensed publisher XML, not synthetic fixtures. The source manifest/README preserve author/title/license/source attribution and acquisition/hash/version caveats. Evaluation checks the exact pinned byte length/hash and own DOI, resolves every returned structural path to its original XML element, compares paragraph/title text, nearest section titles, original element IDs, and table labels, and attaches/reads the exact source. Each also rejects attachment to a different canonical DOI despite an identical bibliography title. RAPTOR's peer-review/editorial sub-article branches are excluded. No clinical finding or retrieval gold label is inferred by these checks.

| Pinned source alias | Returned primary-article blocks | Table blocks | Source identifier |
| --- | ---: | ---: | --- |
| coach | 79 | 2 | Own DOI only |
| whitehall | 88 | 4 | Own DOI only |
| raptor | 48 | 3 | Own DOI only |

These are observed parser counts, not gold medical labels. The coordinator independently parsed the same three sources and reviewed the locator/identity/transaction evidence before accepting E6a.

## Commands and observed evidence

```text
.venv/bin/python -m pytest tests/test_review_documents_acceptance.py -q
68 passed, 5 warnings in 1.34s
```

The five SWIG deprecation warnings are existing PyMuPDF-related warnings. No failed result required an operational fix or relaxed assertion; no evaluator expectation was corrected in E6a. Tests are frozen following this independent gate. The coordinator then ran the complete staged checkout with credentials absent and Hugging Face/Transformers offline: **731 passed, 5 warnings in 38.51s**. Unrelated working-tree retrieval experiments were excluded from that checkout. Scoped Git attributes preserve byte-pinned fixtures and intentional CRLF through checkout. No shared full run was executed for E6a.

Limits: source validation establishes byte identity and quotation location, not clinical entailment, extraction correctness, reviewer independence, or medical validity. PDF extraction has no OCR or password guessing. Stored source hashes are integrity checks for unsigned data. Three real sources constitute a small software pilot; later extraction/verification APIs and independently reviewed retrieval question splits require separate frozen tickets.
