# Capturing, verifying, and replaying a PubMed search

The PubMed adapter captures a search's exact result membership and citation XML, verifies saved captures offline, and imports their records and source artifacts into the review ledger. It uses NCBI ESearch for discovery and EFetch for bibliography records. It does not download full text, load an embedding model, or screen records automatically. The first version supports **at most 10,000 matches** and publishes only a complete validated capture; partial imports, automatic segmentation, and automatic resume are outside this version.

## Standalone API

Configure a developer/contact email and optionally an NCBI API key through your own environment. The adapter does not load `.env` or existing RAG settings. `PubMedClient` makes no request until used; a capture executes a real search, so choose an exact query deliberately.

```python
import os
from src.search.pubmed_search import PubMedClient, capture_pubmed_search

client = PubMedClient(email=os.environ["NCBI_EMAIL"], api_key=os.environ.get("NCBI_API_KEY"))
query = "REPLACE_WITH_YOUR_EXACT_PUBMED_QUERY"
capture = capture_pubmed_search(
    query,
    "data/pubmed-captures/my-new-search",  # Must not already exist.
    client=client,
    sort="pub_date",
    filters={"datetype": "pdat", "mindate": "2020", "maxdate": "2025/12/31"},
    batch_size=200,
)
```

The query is retained exactly, including surrounding whitespace. Date filters and dates above are examples, not recommended search restrictions. Supply only restrictions actually intended for your protocol, or use `filters={}`. `sort` accepts `pub_date` or `relevance`. Date filters accept only `datetype`, `mindate`, and `maxdate`; provide all three together. This version supports date-type tokens `pdat` and `edat`, and date strings as YYYY, YYYY/MM, or YYYY/MM/DD. Dates must be valid calendar dates and the range cannot be inverted. Supplied strings are preserved. Other search restrictions can remain in the exact submitted PubMed query.

NCBI documents `pub_date` as descending publication-date sort and `relevance` as the PubMed default. The adapter explicitly selects `pub_date` by default to avoid depending on a service default. NCBI's generic reference describes date types as database-specific. PubMed Help calls EDAT **Entry Date** and documents modification date under **[lr]**; generic `mdat` support is not enabled until its PubMed API mapping is verified. Inspect the saved query translation and warnings. [NCBI parameters](https://www.ncbi.nlm.nih.gov/sites/books/NBK25499/), [PubMed date-field help](https://pubmed.ncbi.nlm.nih.gov/help/#searching-by-date).

## Command-line workflow

Run from the repository root with the existing Python environment activated. Choose a fresh demo database and create a review project:

```sh
PUBMED_DEMO_DB="data/pubmed-cli-demo.sqlite3"
python review.py --db "$PUBMED_DEMO_DB" create \
  --title "PubMed capture demonstration" --type scoping \
  --question "Can the review preserve a complete captured bibliography?"
```

Copy the returned project's `id` UUID into `PUBMED_PROJECT_ID`. Live capture requires a developer/contact email supplied through `NCBI_EMAIL` or `--email`; the explicit option takes precedence. An optional API key is read only from `NCBI_API_KEY`. Set it through your usual environment/secret-management method if needed. These commands do not read `.env` or RAG settings, and the CLI has no API-key argument.

```sh
PUBMED_PROJECT_ID="COPY_PROJECT_ID_FROM_CREATE_OUTPUT"
PUBMED_CAPTURE_DIR="data/pubmed-captures/new-cli-search"
export NCBI_EMAIL="your-contact@example.org"
```

The following command executes a **live PubMed search**. Replace the query and email with your own values first; the date restriction is an example, not a protocol recommendation. The destination must not already exist. Omit all three date options if no date restriction is intended. `--sort` defaults to `pub_date`, `--batch-size` defaults to 200, and `--import-key` is optional:

```sh
python review.py --db "$PUBMED_DEMO_DB" search-pubmed "$PUBMED_PROJECT_ID" \
  --query "REPLACE_WITH_YOUR_EXACT_PUBMED_QUERY" --output "$PUBMED_CAPTURE_DIR" \
  --sort pub_date --datetype pdat --mindate 2020 --maxdate 2025/12/31 \
  --batch-size 200 --import-key pubmed-cli-demo-v1
```

Success prints JSON with `capture` and `import` objects only after complete capture and ledger import both succeed. The import object includes its `search_run_id` UUID. Validation/capture errors return a nonzero status and a message on stderr. Invalid project/configuration/query/date/batch/output arguments fail before requests. A failed capture does not add a ledger run.

### Recover a completed capture without repeating the search

If capture succeeds but ledger import fails, stderr identifies the retained complete directory and an `import-pubmed` recovery command. Resolve the reported ledger conflict or choose the intended valid project, then replay that directory offline. A retry of `search-pubmed` performs a new search; use the saved capture for recovery.

`verify-pubmed` needs no project, credentials, or ledger. It prints the verified capture as JSON and never opens or creates a database, even when a global `--db` option was supplied. To use the synthetic offline example later in this guide, set `PUBMED_CAPTURE_DIR` to its generated directory and use a fresh demo project; no live command is needed:

```sh
python review.py verify-pubmed "$PUBMED_CAPTURE_DIR"
```

Import the verified capture offline into the project:

```sh
python review.py --db "$PUBMED_DEMO_DB" import-pubmed "$PUBMED_PROJECT_ID" \
  "$PUBMED_CAPTURE_DIR" --import-key pubmed-cli-demo-v1
python review.py --db "$PUBMED_DEMO_DB" history "$PUBMED_PROJECT_ID"
python review.py --db "$PUBMED_DEMO_DB" counts "$PUBMED_PROJECT_ID"
```

For the five-record synthetic capture, a fresh project reports `identified: 5`, `new_records: 5`, and `duplicates: 0`; counts report five unique records awaiting screening. Its history retains the synthetic query, original search time, actual filters, and execution receipt. An identical keyed replay returns the original import result without adding a run or occurrences. Without a key, each replay creates another run and retains its duplicate occurrences.

### Replay a relocated capture under the same key

Keep all source files together. After a successful import, move the complete directory to an unused location, verify it there, and retry the same project/key:

```sh
PUBMED_MOVED_CAPTURE_DIR="data/pubmed-captures/relocated-cli-search"
mv "$PUBMED_CAPTURE_DIR" "$PUBMED_MOVED_CAPTURE_DIR"
python review.py verify-pubmed "$PUBMED_MOVED_CAPTURE_DIR"
python review.py --db "$PUBMED_DEMO_DB" import-pubmed "$PUBMED_PROJECT_ID" \
  "$PUBMED_MOVED_CAPTURE_DIR" --import-key pubmed-cli-demo-v1
python review.py --db "$PUBMED_DEMO_DB" counts "$PUBMED_PROJECT_ID"
```

For identical validated bytes/receipt, the same `search_run_id` and counts return even though the capture moved. The stored original source path remains unchanged. Changed receipt or artifact content under that key fails. Ledger artifact retention also supports deleting the original directory and replaying an exported capture, as shown below.

## What a capture preserves

The adapter executes one ESearch with `retstart=0`, `retmax=10000`, `usehistory=y`, and XML response format. It requires returned Count to match the complete unique PMID list. ESearch normally returns only 20 IDs unless retmax is supplied; the declared count alone does not prove completeness. PubMed's 10,000 limit cannot be bypassed simply by increasing retstart. Larger result sets fail before fetching and require a separately planned, validated segmentation/EDirect workflow. [NCBI search limits](https://ncbiinsights.ncbi.nlm.nih.gov/2022/11/22/updated-pubmed-eutilities-live/).

EFetch receives explicit captured PMIDs in batches of 1–200. Fetch responses may arrive in another order, but their exact own PMID membership must equal the requested batch and complete search set. The combined XML restores search order. Matching record counts alone is insufficient: a response could have one unexpected ID replacing a missing ID. No search is repeated to paginate against a potentially changed database membership. History tokens are preserved for audit, while explicit IDs avoid reliance on those tokens for fetching.

A successful new directory contains:

| File | Contents |
| --- | --- |
| `search.xml` | Exact ESearch response bytes, including translated query, warnings, and history tokens. |
| `batches/0001.xml`, etc. | Exact bytes of each successfully fetched batch. |
| `records.xml` | Validated PubmedArticleSet combining articles/books in captured search order. |
| `receipt.json` | Version 1 receipt with original/translated query, sort, actual filters, search/capture times, ordered PMIDs, database/validated counts, warnings, history, noncredential request parameters, and SHA-256 hashes. |

The returned dictionary provides absolute `directory`, `xml_file`, and `receipt_file` paths plus the receipt object. API keys are excluded from saved parameters and errors. Operational tool/email settings are not search filters. Exact source responses are stored independently of XML reserialization in `records.xml`.

`complete=true` means exact captured membership and fetched bibliography validation passed. It does not establish a comprehensive biomedical search, correct eligibility criteria, full-text availability, or clinical evidence quality. Hashes demonstrate internal file consistency; NCBI has not signed this receipt. PubMed content changes over time, so saved membership and bytes are the durable evidence of this capture.

## Offline fixture capture and parsing replay

The independently constructed fixtures under `tests/fixtures/pubmed/` contain five invented PMIDs, three deliberately reordered EFetch batches, nested text, a collective author, and a book record. They contain no clinical findings. Do not resolve or cite their identifiers.

This example creates a capture entirely offline through an injected client. Use a destination that does not exist:

```python
import json
from pathlib import Path
from src.search.pubmed_search import capture_pubmed_search
from src.review.importers import load_records

fixture_root = Path("tests/fixtures/pubmed")
manifest = json.loads((fixture_root / "manifest.json").read_text(encoding="utf-8"))

class FixtureClient:
    def __init__(self):
        self.fetch_index = 0

    def request(self, endpoint, params):
        if endpoint == "esearch.fcgi":
            return (fixture_root / manifest["search_file"]).read_bytes()
        if endpoint != "efetch.fcgi":
            raise AssertionError(f"Unexpected endpoint: {endpoint}")
        batch = manifest["batches"][self.fetch_index]
        assert params["id"] == ",".join(batch["requested_pmids"])
        self.fetch_index += 1
        return (fixture_root / batch["response_file"]).read_bytes()

capture = capture_pubmed_search(
    manifest["query"],
    "data/pubmed-captures/new-synthetic-demo",
    client=FixtureClient(),
    sort=manifest["sort"],
    filters=manifest["filters"],
    batch_size=manifest["batch_size"],
)
records = load_records(capture["xml_file"], format="pubmed_xml")
assert [record.pmid for record in records] == manifest["ordered_pmids"]
assert capture["receipt"]["reported_count"] == len(records) == 5
```

Parsing replay reads saved XML without network access and does not rerun the search. `load_records` validates bibliography records; it does not verify the complete receipt and source artifacts. Use the verification/import APIs below or the offline CLI commands above for that check. Keep receipt, search response, batches, and combined records together rather than moving only records.xml.

Zero-result searches publish an empty PubmedArticleSet and a complete receipt with count 0; no EFetch is made. Malformed/error XML, entity declarations, conflicting identifiers, short/wrong membership, interrupted fetches, and exhausted network retries fail. Temporary output is cleaned and no completed destination is published. Existing destination files/directories are rejected without modification. A retry after capture failure starts a new search; there is no automatic resume or partial-complete receipt.

## Verify and import a saved capture offline

`verify_pubmed_capture(directory)` reads each allowed artifact once and validates that byte snapshot without requests or modifications. It returns the same directory/XML/receipt paths and receipt shape as capture. `validate_pubmed_artifacts(artifacts)` accepts a relative-filename-to-bytes dictionary and returns `receipt` plus parsed `records`; it makes no file calls. Verification rejects missing/extra assets, symlinked artifact paths, unsafe paths, invalid receipt types/timestamps, hash failures, and receipt/source contradictions. It checks exact PMID membership and combined record **content** against the source batches, so matching counts or recomputing a changed records.xml hash alone cannot bypass validation.

Following the synthetic capture example above:

```python
from src.search.pubmed_search import (
    import_pubmed_capture,
    validate_pubmed_artifacts,
    verify_pubmed_capture,
)
from src.review.store import ReviewStore

verified = verify_pubmed_capture(capture["directory"])
assert verified["receipt"]["pmids"] == manifest["ordered_pmids"]

demo_db = "data/pubmed-replay-demo.sqlite3"
with ReviewStore(demo_db) as store:
    project = store.create_project(
        "Synthetic PubMed replay demonstration",
        "scoping",
        "Can captured software-fixture records retain their source provenance?",
    )
    imported = import_pubmed_capture(
        store,
        project["id"],
        capture["directory"],
        idempotency_key="synthetic-pubmed-demo-v1",
    )
    assert imported["identified"] == imported["new_records"] == 5
    assert imported["duplicates"] == 0
```

The import helper performs its own validation of one loaded byte snapshot, then parses/stores those same bytes. It does not trust a previous verification call or reopen XML independently. `SearchRunSpec` carries the original query, ESearch execution time, actual user filters, reported count, combined-file path/hash, and the full receipt in its dedicated `execution` field. History retains the original search time while recording a separate ledger import timestamp. Sort, translation, warnings, and request metadata belong to execution provenance rather than user filters.

SQLite stores the exact receipt, search response, batch responses, and combined XML as immutable artifact bytes in the same transaction as the run and record occurrences. Invalid artifacts or conflicting canonical identifiers roll back the whole import. Identical keyed capture retries return the existing result; changing a capture's directory alone does not create a different fingerprint. Changed receipt, artifact bytes, or other supplied source metadata under the same key fail. The original stored source path remains unchanged. Generic bibliography imports retain their existing strict metadata/path behavior and have no capture assets.

## Reopen, export, and replay retained artifacts

After a successful import, the original capture directory may be moved or deleted: ledger provenance no longer depends on that path remaining available. Reopen the ledger and validate its retained bytes:

```python
with ReviewStore(demo_db) as store:
    retained = store.get_search_artifacts(project["id"], imported["search_run_id"])
    replay = validate_pubmed_artifacts(retained)
    assert [record.pmid for record in replay["records"]] == manifest["ordered_pmids"]
    exported = store.export_project(project["id"], "data/pubmed-replay-demo-export")
    assert exported["counts"]["records_identified"] == 5
    assert exported["counts"]["all_checks_passed"] is True

exported_capture = (
    Path(exported["directory"]) / "search_captures" / imported["search_run_id"]
)
verify_pubmed_capture(exported_capture)
```

Export includes the normal nine ledger files plus `search_captures/<search_run_id>/receipt.json`, `search.xml`, `records.xml`, and the original `batches/*.xml`. `project.json` adds a `search_artifacts` manifest with run ID, relative asset name, SHA-256, byte size, and export path; `search_runs.csv` includes execution provenance as JSON. Generic-only exports still have nine files, with no capture assets. Stored hashes are checked before output, and artifacts are read in the same SQLite snapshot as the records/counts. Unrelated files in an export destination are preserved.

An exported capture directory can be verified or passed to `import_pubmed_capture` for offline replay into another review project. Its original receipt/search time and raw source bytes remain intact; the new project/run receives its own import timestamp and conservative deduplication. In the same project, the same explicit key and identical validated receipt/bytes return the original run even when replaying from a moved or exported directory. The stored original path remains audit metadata; generic file imports still reject changed path metadata under the same key. Exported counts remain record/report counts; study linkage and `included_studies` are still unavailable.

Checksums and cross-file validation establish internal consistency, not a provider signature or proof that a query was methodologically comprehensive. A capture's `complete` flag certifies its exact saved search membership; human review of the query translation and warnings remains necessary.

## Network behavior

Requests use fixed NCBI HTTPS E-utilities endpoints and URL-encoded HTTP POST bodies. The client serializes attempts, throttles at 3 requests/second without an API key or 10/second with one, and performs bounded retries for transient 429/5xx or transport failures. It honors Retry-After when available and otherwise backs off. Other HTTP errors and malformed returned data fail rather than retrying an interpreted search.

Rate limiting covers one client instance, not all processes sharing an IP or API key. NCBI applies limits across those shared sources; concurrent users may need coordination. NCBI encourages larger jobs on weekends or weekday 21:00–05:00 Eastern time and developer tool/email identification. [NCBI usage and API-key policy](https://www.ncbi.nlm.nih.gov/sites/books/NBK25497/).

PubMed provides citation/abstract metadata; full text is a separate acquisition task. Abstracts may have copyright restrictions. See [NCBI's disclaimer and copyright notice](https://www.ncbi.nlm.nih.gov/home/about/policies/).
