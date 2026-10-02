# Durable source documents

The review ledger can retain a report's original source bytes and exact quotation blocks through its Python API and `attach-source`, `documents`, and `source-blocks` CLI commands. Source attachment does not change screening or retrieval status. Each attachment creates a new immutable version; the most recently attached version is active for that report. Its integer version is a local sequence, not a publisher version number. The [executable evidence guide](verified-evidence.md) demonstrates the complete offline CLI workflow.

## Attach and inspect a source

Use project and record IDs returned by the review CLI, and choose the source format explicitly. This example reads the file once, then parses, hashes and stores that same byte snapshot. Source URLs and publisher version labels are optional provenance supplied by the reviewer; the ledger does not fetch them.

```python
from pathlib import Path
from src.review.store import ReviewStore

with ReviewStore("data/reviews.sqlite3") as store:
    document = store.attach_document(
        project_id, record_id, Path("article.xml").read_bytes(), "jats_xml",
        reviewer="reviewer-1", reason="Checked this source against the report",
        filename="article.xml", source_url=publisher_url,
        version_label="Enter the publisher's version description",
    )
    blocks = store.get_source_blocks(project_id, document["id"])
    original_bytes = store.get_document_bytes(project_id, document["id"])
    all_versions = store.list_documents(project_id, record_id)
```

An explicit own-article DOI/PMID in JATS is normalized and retained. A contradiction with the report's known identifier rejects attachment. Cited-reference identifiers never supply report identity. When a source lacks usable identifiers, the reviewer establishes its association with the report; title similarity or PDF text does not automatically prove identity.

If a later bibliography import supplies a previously unknown identifier that contradicts the retained source, structured evidence receives `source_identity_conflict` and leaves verified output. Original imports, source bytes and review history remain available; a correct new source and independently checked evidence revision can restore verification.

## Source formats and locators

| Format | Canonical blocks | Locator |
| --- | --- | --- |
| `txt` | One UTF-8/BOM-decoded block; exact line endings and Unicode remain unchanged. | `text_block`, ordinal 1 |
| `jats_xml` | Main article title, abstract/body paragraphs and body tables; inline text is concatenated before whitespace collapse. | `xml_element`, structural path, optional element/section/table labels |
| `pdf` | Sorted PyMuPDF text for every actual PDF page, including blank pages. | `pdf_page`, actual one-based page position |

XML table blocks contain label, caption, tab-separated cells for each row, and table footnotes, separated by newlines. They do not infer spanning-cell semantics or image contents. Reference lists and sub-article peer-review/editorial correspondence are excluded from finding blocks; original XML bytes remain complete. External DTDs are ignored, and entity declarations and malformed/error XML are rejected.

PDF parsing uses the existing PyMuPDF dependency lazily. Encrypted, corrupt or entirely text-empty PDFs are rejected. There is no OCR. Printed journal page labels can differ from the actual PDF positions recorded here.

Each block has an ID, ordinal, canonical text and typed locator. A quotation uses half-open character offsets into that exact canonical text: `block["text"][start:end]`. Offsets count Unicode code points, not UTF-8 bytes. Block IDs belong to a specific document version; reuse of a structural path in a later version does not establish unchanged text.

## Durability and export

SQLite retains source bytes, parser identity/options/runtime versions, source and canonical-block SHA-256 hashes, source identifiers, reviewer and attachment reason. Reads verify stored byte/block integrity and need no original file or parser initialization. Repeated attachment retains previous versions, even when bytes match.

Project exports with sources include `documents`, `source_blocks` and `document_artifacts` in `project.json`, plus `documents.csv`, `source_blocks.json` and exact files under `documents/<document_id>/<filename>`. Every version is included in the same SQLite snapshot as screening, study linkage and search history. Unchanged exports are deterministic; separate file replacement is not an atomic directory publication. Counts retain their existing meanings.

Hashes identify retained representations and detect accidental corruption. This is an unsigned local ledger: consistent external changes to data and hashes cannot be authenticated. Source anchoring proves where quoted text occurs; determining whether it supports an extracted finding still requires reviewer judgment.
