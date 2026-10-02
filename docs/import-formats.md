# Importing bibliography records into a review project

The review ledger imports saved citation exports without making network requests or loading an embedding model. It stores search/import history and screening decisions in SQLite. JSON, RIS, and PubMed XML are supported; importing records does not retrieve full text or execute a database search.

Run the commands below from the repository root with the existing Python environment activated. Use a fresh database path for the demonstration. All files under `examples/review/` contain deliberately synthetic metadata, authors, and identifiers; they describe no real publications or clinical findings. Do not resolve or cite those identifiers. `expected-import-counts.json` is a count manifest, not an importable bibliography.

## Canonical JSON

The file must contain a UTF-8 JSON **array** of objects. An empty array is a valid zero-result export. A UTF-8 byte-order mark is accepted. Field names are case-sensitive.

| Field | Type | Import behavior |
| --- | --- | --- |
| `title` | Nonempty string | Required; surrounding whitespace is trimmed in the parsed record. |
| `authors` | Array of nonempty strings | Optional, default `[]`; order is retained. A collective author is one string. |
| `year` | Integer from 1 to 9999, or null | Optional; strings and booleans are rejected. |
| `doi` | String or null | Optional; common DOI prefixes and DOI URL forms are validated. |
| `pmid` | String or null | Optional; digit strings, `PMID:` prefixes, and PubMed URL forms are validated. Use a JSON string, not a number. |
| `abstract` | String | Optional, default `""`. |
| `url` | String | Optional, default `""`; kept as metadata without fetching it. |
| `source_id` | String | Optional, default `""`; a database-specific accession or source identifier. |
| Other fields | JSON values | Preserved in `raw`, including unknown fields and any supplied `raw` object. |

Null is accepted only for `year`, `doi`, and `pmid`. Empty DOI/PMID strings are treated as missing identifiers. Duplicate JSON keys, non-finite numbers, missing titles, malformed identifiers, and invalid field types fail the whole load with filename and record/line context. Unknown fields are retained rather than treated as canonical identifiers.

The example [`synthetic-records.json`](../examples/review/synthetic-records.json) has six occurrences: one DOI duplicate, one complete no-identifier fallback duplicate, and four unique records.

## RIS

RIS records start with a nonempty `TY` type and end with an empty `ER` tag. Standard tagged lines such as `TI  - Title` are accepted, including ordinary one- or two-space separators before the hyphen. Untagged continuation lines continue the preceding field, which supports multiline abstracts. A missing record boundary or malformed tag fails clearly. An empty RIS file is accepted as zero records.

| RIS tags | Parsed field |
| --- | --- |
| `TI`, otherwise `T1` | Title |
| Repeated `AU` / `A1` | Authors in original tag order |
| `PY`, otherwise `Y1` | First four-digit publication year in the date value |
| `DO` / `DI` | DOI; conflicting repeated DOI values are rejected |
| `AB` / `N2` | Abstract paragraphs joined with newlines |
| `UR` | First nonempty URL |
| `AN`, otherwise `ID` | Source accession/identifier |
| `DB` / `DP` | Database/source metadata used only for the PMID rule below |

A numeric accession number is **not automatically a PMID**. `AN` is also interpreted as PMID only when `DB` or `DP` explicitly equals `PubMed`, `NCBI PubMed`, or `PubMed (NCBI)`, ignoring case and surrounding whitespace. `MEDLINE` alone and `PubMed Central` do not satisfy this rule. An optional `PMID:` prefix in that accession is accepted. The accession also remains in `source_id`; every original tag remains in raw provenance. Explicit `PM` tags are parsed as PMID independently of accession metadata. Conflicting repeated PMID values are rejected.

The parser keeps all tags, repeated values, their order, and the original record text in `raw`. It does not validate every optional tag against a complete RIS schema or attempt to repair structurally incomplete records. The example [`synthetic-record.ris`](../examples/review/synthetic-record.ris) represents synthetic record B from the JSON fixture.

RIS tag mappings follow common reference-manager practice documented in the [Zotero RIS translator](https://github.com/zotero/translators/blob/master/RIS.js). The strict rule for treating an accession as PMID is this engine's conservative policy.

## PubMed XML

The importer accepts `PubmedArticleSet`, `PubmedBookArticleSet`, and `MedlineCitationSet` containers, plus standalone `PubmedArticle`, `PubmedBookArticle`, or `MedlineCitation` records. Empty supported containers are valid zero-result exports. Other root types and unsupported children, including error/deletion records, are rejected instead of silently omitted. This is PubMed citation XML support; PMC/JATS full-text XML and publisher-submission `ArticleSet` XML are separate formats.

- Nested title and abstract markup is converted to plain text while preserving its text content. Structured abstract `Label` values become `LABEL: text` paragraphs separated by newlines. The original XML preserves markup and other abstracts/fields.
- Personal authors use `LastName, ForeName`, with initials when the full given name is absent. Collective authors retain `CollectiveName`. Author order is retained.
- Publication year comes from the issue's `PubDate/Year` or the first four-digit year in `MedlineDate`; `ArticleDate/Year` is a fallback. Book publication dates are read from `Book/PubDate`.
- PMID comes from the citation's own `PMID` and PubMed article identifier list. DOI comes from the article's own DOI `ArticleId` and `ELocationID`. Conflicting IDs fail; IDs belonging to cited references are not treated as IDs of the imported record.
- A PubMed URL is constructed from the PMID when present. Raw provenance includes the complete parsed citation XML and a structured element tree containing attributes, text, and children. XML serialization can change quote/namespace formatting; the source-file checksum identifies the original file bytes.
- External DTD declarations are ignored without fetching them. Entity declarations are rejected before parsing; external entity and network references are never resolved. This is an offline parser, not a DTD/schema validator.

The example [`synthetic-record.xml`](../examples/review/synthetic-record.xml) represents the same synthetic record B as the RIS example, with nested title/abstract text and a collective author. Field choices are based on [NLM's MEDLINE/PubMed XML element documentation](https://www.nlm.nih.gov/bsd/licensee/data_elements_doc.html), [NLM's article-date guidance](https://www.nlm.nih.gov/bsd/licensee/elements_article_source.html), and the [PubMed book-record schema](https://dtd.nlm.nih.gov/ncbi/pubmed/doc/out/190101/el-PubmedBookArticle.html).

## Identity and provenance

Deduplication is scoped to one project. The ledger first compares normalized DOI or PMID. DOI URL/prefix forms and case normalize to the same DOI; PubMed URLs/prefixes and leading zeros normalize to a digit-only PMID. Malformed identifiers fail, and a conflict between existing DOI/PMID identities rolls back the entire import.

Only when **both** records lack DOI and PMID does the ledger use an exact normalized title, publication year, and first-author identity. All three are required. Text normalization collapses whitespace, ignores case, and applies Unicode NFKC normalization. No fuzzy matching or title-only merging is performed. Distinct arXiv report/version identifiers remain separate unless a strong identifier matches. Different DOI/PMID-bearing records remain separate even if titles match; missing strong identifiers do not by themselves justify merging with an identified record.

Every supplied occurrence is retained, including duplicates, and points to its immutable import/search run and canonical record ID. A canonical record fills missing metadata from later matching occurrences without overwriting conflicting populated values. Inspect `occurrences` in the exported `project.json` or `occurrences.csv` to see those original versions; canonical records alone cannot show every metadata conflict. Review decisions attach to the canonical record, not an individual import occurrence.

These identities reconcile bibliography records/reports. Multiple reports can concern one underlying study, but study linkage is not implemented; `included_studies` remains null and `study_linkage_available` false.

## Search history and partial exports

An import run should record the database/platform in `--source`, the exact executed query in `--query`, the actual search date/time in `--searched-at`, and database filters as a JSON object in `--filters-json`. The ledger preserves supplied query/date text rather than rewriting it. Supply an ISO date or datetime, including its timezone when known. Omit unknown query/date flags; their fields remain null. The internal UTC import timestamp records when the ledger was written, not when the database was searched.

The CLI computes SHA-256 from the source-file bytes and stores `source_sha256`, the source path in `source_file`, and the selected format. A checksum identifies an imported file; it does not prove that its export covered all database results. Notes can explain manual exports, database limits, or search uncertainties. The importer does not infer a query or a complete search history from a bibliography file.

`--reported-count` records the result count reported by the source, when known. It cannot be smaller than the imported occurrence count. If the source reports 1500 results but the file contains 200 records, flow totals count **200 imported occurrences**, while history/export retains the separately reported 1500. This partial export is not a complete database search. An omitted reported count means unknown, not zero. Do not sum overlapping database-reported totals and present them as reviewed records.

Without `--import-key`, each invocation is a new run, even when the file is unchanged. Reimporting an unchanged six-record file adds six occurrences and six duplicates after its initial import; it preserves the four canonical records. An explicit key prevents accidental duplicate runs: retrying an identical import command with the same key returns the original run/result without adding history or counts. Changing records, source path/checksum, query, dates, notes, or other supplied search metadata under that key fails. Keys are scoped to projects; genuine later searches should use a new key or omit it.

## Reproduce the synthetic import counts

Choose a new database path and create one project:

```sh
REVIEW_DEMO_DB="data/demo-reviews.sqlite3"
python review.py --db "$REVIEW_DEMO_DB" create \
  --title "Synthetic bibliography demonstration" --type scoping \
  --question "Can the ledger preserve and reconcile synthetic import records?" \
  --protocol "Software demonstration only; no research synthesis."
```

Copy the UUID from the returned project's `id` field into `REVIEW_DEMO_PROJECT_ID`. The named placeholder below must be replaced with that actual value:

```sh
REVIEW_DEMO_PROJECT_ID="COPY_PROJECT_ID_FROM_CREATE_OUTPUT"
python review.py --db "$REVIEW_DEMO_DB" import "$REVIEW_DEMO_PROJECT_ID" \
  examples/review/synthetic-records.json --source "Synthetic JSON fixture" \
  --notes "Software fixture only; no database search was executed." \
  --import-key demo-json-v1
```

The result reports `identified: 6`, `new_records: 4`, and `duplicates: 2`, plus an actual `search_run_id` UUID. Retry exactly that same command to demonstrate idempotency: the same run/result returns and counts stay unchanged. Query and searched-at are deliberately omitted because this was not an executed database search.

Then import the equivalent RIS/XML occurrences and a zero-result run:

```sh
python review.py --db "$REVIEW_DEMO_DB" import "$REVIEW_DEMO_PROJECT_ID" \
  examples/review/synthetic-record.ris --source "Synthetic RIS fixture"
python review.py --db "$REVIEW_DEMO_DB" import "$REVIEW_DEMO_PROJECT_ID" \
  examples/review/synthetic-record.xml --format pubmed_xml --source "Synthetic PubMed XML fixture"
python review.py --db "$REVIEW_DEMO_DB" import "$REVIEW_DEMO_PROJECT_ID" \
  examples/review/zero-results.json --source "Synthetic zero-result fixture"
python review.py --db "$REVIEW_DEMO_DB" history "$REVIEW_DEMO_PROJECT_ID"
python review.py --db "$REVIEW_DEMO_DB" records "$REVIEW_DEMO_PROJECT_ID"
python review.py --db "$REVIEW_DEMO_DB" counts "$REVIEW_DEMO_PROJECT_ID"
```

There are now four runs, eight raw occurrences, four duplicate occurrences removed, and four unique records awaiting title/abstract screening. Check each intermediate result against [`expected-import-counts.json`](../examples/review/expected-import-counts.json). `history` exposes exact source/query/date/checksum metadata; `records` supplies the UUIDs needed by screening commands. Zero-result runs remain visible without changing counts. Rerunning the **unkeyed** RIS/XML commands creates additional runs, so repeatable CLI execution of this whole example requires a fresh database or explicit keys on every import.

For a real saved database export, replace the placeholders below with the actual project ID, file path, database/platform, executed query, search date/time, and reported result count. Omit any unknown fields rather than inventing them:

```sh
python review.py --db "PATH_TO_REVIEW_DATABASE" import "ACTUAL_PROJECT_ID" \
  "PATH_TO_SAVED_PUBMED_EXPORT.xml" --format pubmed_xml --source "PubMed" \
  --query "EXACT_QUERY_EXECUTED_IN_PUBMED" --searched-at "ACTUAL_ISO_SEARCH_DATE_OR_DATETIME" \
  --filters-json '{"language": "English"}' --reported-count 1500 \
  --notes "Replace this note and all placeholders with the actual search/export details." \
  --import-key "UNIQUE_KEY_FOR_THIS_SEARCH_AND_EXPORT"
```

The language filter and result count above are examples, not recommended search restrictions or assertions about your source. Record only the filters/count actually observed. Imports and conservative identity matching prepare a screening ledger; they do not establish review completeness, methodological eligibility, risk of bias, or clinical evidence quality.
