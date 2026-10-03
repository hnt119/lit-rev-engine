# Getting started with the offline review ledger

This walkthrough creates a review project, imports a saved bibliography, records manual screening and full-text status, and exports an auditable snapshot. It uses only Python 3.12's standard library. You need no paid API, model download, third-party package, or network connection.

The supplied sample contains **six synthetic occurrences, two duplicate occurrences, and four unique records**. Its authors, titles, DOI and PMID values are invented software fixtures. They are not publications or medical evidence; do not resolve or cite their identifiers. The decisions below exercise the CLI, not clinical eligibility. Recording `retrieved` does not download or attach a document.

## 1. Prepare an isolated demonstration

Open a bash or zsh terminal in the repository root, the directory containing `review.py`. Run every block below in order in the same shell. Python 3.12 must already be installed; if its executable has another name or path, change only `REVIEW_PYTHON` to that executable. The version check stops an unsupported interpreter before creating data.

```sh
set -e
REVIEW_PYTHON=python3.12
"$REVIEW_PYTHON" -B -S -c 'import sys; assert sys.version_info[:2] == (3, 12), "Use Python 3.12"; print(sys.version)'
REVIEW_DEMO_DIR="$("$REVIEW_PYTHON" -B -S -c 'import tempfile; print(tempfile.mkdtemp(prefix="lre-getting-started-"))')"
REVIEW_DEMO_DB="$REVIEW_DEMO_DIR/review.sqlite3"
printf 'Demo directory: %s\n' "$REVIEW_DEMO_DIR"
```

All demo database and output files stay in that new temporary directory. `-B` avoids writing Python bytecode into the checkout; `-S` skips installed site packages. Every ledger command supplies `--db` **before** its command, so the default repository `data/reviews.sqlite3` is not used. Keep the printed directory path if you want to inspect the result later; temporary storage is not suitable for a real review.

The offline ledger, lexical passage retrieval, and TXT/JATS source parsing use the standard library. PDF source attachment needs PyMuPDF. The separate PDF indexing/RAG tools need the [runtime dependencies and configuration](../README.md#requirements-and-installation); their embedding pipeline loads a model, and answer generation uses Agnes. Those dependencies are unnecessary here. Optional [Kaggle Qwen retrieval](qwen-cloud.md) uses offline job export/import and a separate free GPU notebook; this walkthrough invokes neither service nor model.

## 2. Create a project and import the sample

The CLI returns JSON. Save the result, then let Python read its actual project UUID; no placeholder IDs or `jq` are needed.

```sh
"$REVIEW_PYTHON" -B -S review.py --db "$REVIEW_DEMO_DB" create \
  --title "Synthetic ledger walkthrough" --type scoping \
  --question "Can a local ledger preserve a synthetic screening audit?" \
  --protocol "Software drill: include record A, exclude record B, leave other records pending." \
  > "$REVIEW_DEMO_DIR/project-created.json"
REVIEW_PROJECT_ID="$("$REVIEW_PYTHON" -B -S -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["id"])' "$REVIEW_DEMO_DIR/project-created.json")"
"$REVIEW_PYTHON" -B -S -m json.tool "$REVIEW_DEMO_DIR/project-created.json"
```

Import the same file twice with the same `--import-key`. An identical keyed retry returns the original run; it does not add occurrences. The loop saves each response separately for the final audit.

```sh
for REVIEW_IMPORT_OUTPUT in import.json import-retry.json; do
  "$REVIEW_PYTHON" -B -S review.py --db "$REVIEW_DEMO_DB" import "$REVIEW_PROJECT_ID" \
    examples/review/synthetic-records.json --source "Synthetic JSON fixture" \
    --notes "Software fixture only; no database search was executed." \
    --import-key getting-started-v1 > "$REVIEW_DEMO_DIR/$REVIEW_IMPORT_OUTPUT"
done
"$REVIEW_PYTHON" -B -S -m json.tool "$REVIEW_DEMO_DIR/import.json"
```

Expected: `identified: 6`, `new_records: 4`, `duplicates: 2`, and the same `search_run_id` in both responses. A DOI URL/case variant matches record A; a title/year/first-author variant matches record C. The other record with C's title has a different first author and remains separate. All six original occurrences are retained.

Without an import key, each invocation creates another historical run, even for unchanged input. A changed file or changed metadata under an existing key fails. Query and search date are omitted here because no search occurred. For real saved exports, record the actual source, exact query, search date, filters and reported count; see [Import formats and provenance](import-formats.md).

## 3. Inspect history and select actual record IDs

`history` lists immutable import/search runs, including the source checksum. `records` lists canonical records and their current states. Before screening, all four records are `pending` at title/abstract, `not_requested` for full text, and `pending` at full text.

```sh
"$REVIEW_PYTHON" -B -S review.py --db "$REVIEW_DEMO_DB" history "$REVIEW_PROJECT_ID" \
  > "$REVIEW_DEMO_DIR/history.json"
"$REVIEW_PYTHON" -B -S review.py --db "$REVIEW_DEMO_DB" records "$REVIEW_PROJECT_ID" \
  > "$REVIEW_DEMO_DIR/records-before.json"
"$REVIEW_PYTHON" -B -S -m json.tool "$REVIEW_DEMO_DIR/history.json"
"$REVIEW_PYTHON" -B -S -m json.tool "$REVIEW_DEMO_DIR/records-before.json"
REVIEW_RECORD_A="$("$REVIEW_PYTHON" -B -S -c 'import json,sys; rows=json.load(open(sys.argv[1], encoding="utf-8")); print(next(row["id"] for row in rows if row["doi"] == "10.99999/lre-demo-a"))' "$REVIEW_DEMO_DIR/records-before.json")"
REVIEW_RECORD_B="$("$REVIEW_PYTHON" -B -S -c 'import json,sys; rows=json.load(open(sys.argv[1], encoding="utf-8")); print(next(row["id"] for row in rows if row["pmid"] == "999999991"))' "$REVIEW_DEMO_DIR/records-before.json")"
printf 'Actual record A UUID: %s\nActual record B UUID: %s\n' "$REVIEW_RECORD_A" "$REVIEW_RECORD_B"
```

The Python selectors identify the two known fixture records in the returned JSON. They perform no network lookup or eligibility inference. In a real review, inspect the returned metadata and choose the actual record you have reviewed.

## 4. Record manual screening and full-text status

Follow the demonstration protocol: include A at title/abstract, record a requested then retrieved status, and include A at full text. Exclude B at title/abstract with a reason. These statuses and reasons are declared software demonstration inputs; no publication or full text is fetched.

```sh
"$REVIEW_PYTHON" -B -S review.py --db "$REVIEW_DEMO_DB" screen "$REVIEW_PROJECT_ID" "$REVIEW_RECORD_A" \
  --stage title_abstract --decision include --reviewer demo-reviewer \
  --reason "Demo protocol selects the DOI exercise for the inclusion path."
"$REVIEW_PYTHON" -B -S review.py --db "$REVIEW_DEMO_DB" fulltext "$REVIEW_PROJECT_ID" "$REVIEW_RECORD_A" \
  --status requested --reviewer demo-reviewer --reason "Scripted request for the software drill."
"$REVIEW_PYTHON" -B -S review.py --db "$REVIEW_DEMO_DB" fulltext "$REVIEW_PROJECT_ID" "$REVIEW_RECORD_A" \
  --status retrieved --reviewer demo-reviewer \
  --reason "Scripted retrieved status only; no publication was downloaded."
"$REVIEW_PYTHON" -B -S review.py --db "$REVIEW_DEMO_DB" screen "$REVIEW_PROJECT_ID" "$REVIEW_RECORD_A" \
  --stage full_text --decision include --reviewer demo-reviewer \
  --reason "Scripted full-text inclusion under the software drill protocol."
"$REVIEW_PYTHON" -B -S review.py --db "$REVIEW_DEMO_DB" screen "$REVIEW_PROJECT_ID" "$REVIEW_RECORD_B" \
  --stage title_abstract --decision exclude --reviewer demo-reviewer \
  --reason "Demo protocol excludes the adapter-only exercise from the inclusion path."
"$REVIEW_PYTHON" -B -S review.py --db "$REVIEW_DEMO_DB" decisions "$REVIEW_PROJECT_ID" \
  > "$REVIEW_DEMO_DIR/decisions.json"
"$REVIEW_PYTHON" -B -S review.py --db "$REVIEW_DEMO_DB" records "$REVIEW_PROJECT_ID" \
  > "$REVIEW_DEMO_DIR/records-after.json"
"$REVIEW_PYTHON" -B -S review.py --db "$REVIEW_DEMO_DB" counts "$REVIEW_PROJECT_ID" \
  > "$REVIEW_DEMO_DIR/counts.json"
"$REVIEW_PYTHON" -B -S -m json.tool "$REVIEW_DEMO_DIR/decisions.json"
"$REVIEW_PYTHON" -B -S -m json.tool "$REVIEW_DEMO_DIR/counts.json"
```

Expected current counts:

| Field | Value |
| --- | ---: |
| `records_identified` | 6 |
| `duplicate_records_removed` | 2 |
| `unique_records` | 4 |
| `records_awaiting_screening` | 2 |
| `records_screened` | 2 |
| `records_excluded` | 1 |
| `records_included_for_full_text` | 1 |
| `reports_sought_for_retrieval` | 1 |
| `reports_retrieved` | 1 |
| `reports_assessed` | 1 |
| `reports_included` | 1 |
| `included_studies` | null |
| `study_linkage_available` | false |
| `all_checks_passed` | true |

The other pending/unresolved/exclusion counters are zero. There are three screening decisions and two retrieval events. Two records remain unscreened, so this is an incomplete review. One included report does not establish one included study; this demo creates no study links.

Title/abstract inclusion is required before full-text retrieval, and `retrieved` is required before full-text assessment. Exclusion and `not_retrieved` require reasons. History is append-only: the latest decision per reviewer determines current screening; disagreement becomes `conflict`, and `uncertain` remains unresolved. `adjudicate` resolves existing decisions with a reason; later reviews invalidate that resolution. Once retrieval starts, title/abstract revisions must preserve inclusion, and retrieved status is terminal in this version. The CLI does not enforce a protocol's required reviewer count.

## 5. Export twice and audit the saved files

Export the unchanged ledger into two fresh directories. The export contains `project.json`, `counts.json`, and CSV files for records, search runs, occurrences, decisions, retrieval events, counts and exclusions. CSV prefixes potentially executable spreadsheet-formula text with a single quote; JSON preserves original values. Source/study/evidence files are added when those features have data.

```sh
"$REVIEW_PYTHON" -B -S review.py --db "$REVIEW_DEMO_DB" export "$REVIEW_PROJECT_ID" "$REVIEW_DEMO_DIR/export-a" \
  > "$REVIEW_DEMO_DIR/export-result-a.json"
"$REVIEW_PYTHON" -B -S review.py --db "$REVIEW_DEMO_DB" export "$REVIEW_PROJECT_ID" "$REVIEW_DEMO_DIR/export-b" \
  > "$REVIEW_DEMO_DIR/export-result-b.json"
```

Run this independent audit using only Python's JSON/CSV/file readers. It reads the exported artifacts, not the ledger implementation. It verifies the known fixture totals, raw occurrences, states, history and exclusion reason, then compares every exported file byte for byte. Determinism applies to unchanged contents of the same ledger; fresh walkthrough runs generate different UUIDs and timestamps.

```sh
"$REVIEW_PYTHON" -B -S - "$REVIEW_DEMO_DIR" <<'PY'
import csv, hashlib, json, sys
from collections import Counter
from pathlib import Path

folder = Path(sys.argv[1])
def read(name):
    return json.loads((folder / name).read_text(encoding="utf-8"))
def rows(name):
    with (folder / "export-a" / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))

imported = read("import.json")
assert imported == read("import-retry.json")
assert {key: imported[key] for key in ("identified", "new_records", "duplicates")} == {
    "identified": 6, "new_records": 4, "duplicates": 2,
}
bundle = read("export-a/project.json")
records, occurrences = bundle["records"], bundle["occurrences"]
assert len(records) == 4 and len(occurrences) == 6
assert sorted(Counter(row["record_id"] for row in occurrences).values()) == [1, 1, 2, 2]
assert len(occurrences) - len({row["record_id"] for row in occurrences}) == 2
assert bundle["search_runs"] == read("history.json") and len(bundle["search_runs"]) == 1
run = bundle["search_runs"][0]
assert run["id"] == imported["search_run_id"]
assert run["source_sha256"] == hashlib.sha256(Path("examples/review/synthetic-records.json").read_bytes()).hexdigest()
assert run["query"] is None and run["searched_at"] is None
assert all(row["title_abstract_state"] == "pending" for row in read("records-before.json"))
assert records == read("records-after.json")
a = next(row for row in records if row["doi"] == "10.99999/lre-demo-a")
b = next(row for row in records if row["pmid"] == "999999991")
assert (a["title_abstract_state"], a["full_text_status"], a["full_text_state"]) == ("include", "retrieved", "include")
assert (b["title_abstract_state"], b["full_text_status"], b["full_text_state"]) == ("exclude", "not_requested", "pending")
assert Counter(row["title_abstract_state"] for row in records) == {"pending": 2, "include": 1, "exclude": 1}
expected = {
    "records_identified": 6, "duplicate_records_removed": 2, "unique_records": 4,
    "records_awaiting_screening": 2, "records_screened": 2, "records_excluded": 1,
    "records_included_for_full_text": 1, "reports_sought_for_retrieval": 1,
    "reports_retrieved": 1, "reports_assessed": 1, "reports_included": 1,
    "records_screening_unresolved": 0, "reports_awaiting_request": 0,
    "reports_not_retrieved": 0, "reports_awaiting_retrieval": 0,
    "reports_awaiting_assessment": 0, "reports_excluded": 0,
    "reports_assessment_unresolved": 0, "included_studies": None,
    "study_linkage_available": False, "all_checks_passed": True,
}
counts = bundle["counts"]
assert counts == read("counts.json") == read("export-a/counts.json")
assert {key: counts[key] for key in expected} == expected
assert len(counts["reconciliation"]) == 7 and all(counts["reconciliation"].values())
history = read("decisions.json")
assert bundle["decisions"] == history["decisions"] and len(history["decisions"]) == 3
assert bundle["retrieval_events"] == history["retrieval_events"]
assert [event["status"] for event in history["retrieval_events"]] == ["requested", "retrieved"]
assert len(rows("records.csv")) == 4 and len(rows("occurrences.csv")) == 6
assert len(rows("decisions.csv")) == 3 and len(rows("retrieval_events.csv")) == 2
exclusions = rows("exclusions.csv")
assert len(exclusions) == 1 and exclusions[0]["record_id"] == b["id"]
assert exclusions[0]["stage"] == "title_abstract"
assert exclusions[0]["reason"] == "Demo protocol excludes the adapter-only exercise from the inclusion path."
first = {path.relative_to(folder / "export-a"): path.read_bytes() for path in (folder / "export-a").rglob("*") if path.is_file()}
second = {path.relative_to(folder / "export-b"): path.read_bytes() for path in (folder / "export-b").rglob("*") if path.is_file()}
assert set(first) == {Path(name) for name in read("export-result-a.json")["files"]}
assert first == second and len(first) == 9
print("PASS: 6 occurrences / 2 duplicates / 4 records; 1 included report, 1 TA exclusion, 2 pending; 9 identical export files.")
print("Inspect the retained temporary demo:", folder)
PY
```

Keep `review.sqlite3` if you want to reopen this demonstration: set `REVIEW_DEMO_DB` to its printed full path and obtain project IDs with `projects`. The database is the editable ledger; exported JSON/CSV are snapshots for inspection. Exports use one consistent database snapshot, but replacement of separate output files is not an atomic directory publication. For a real review, choose a durable database path outside the temporary directory and preserve backups.

## 6. Use the ledger for a real review

1. Define the question, protocol and eligibility rules before screening. Create a new project and durable database; retain the actual source search/export details. Check raw occurrences and conservative DOI/PMID or no-identifier matches rather than assuming deduplication establishes study identity. [Import formats](import-formats.md) covers partial exports and provenance. [PubMed capture and offline replay](pubmed-search.md) describes the separate explicit search workflow; no live search is needed for this walkthrough.
2. Have reviewers inspect the actual titles/abstracts and full texts. Record their real identities, decisions, exclusion reasons and retrieval outcomes. Resolve uncertainty and disagreement according to the protocol. Status flags record declarations; they do not acquire full text, make eligibility judgments, or authenticate reviewers.
3. Check which reports describe the same underlying study, and record reasoned complete association sets. Several reports can describe one study; one report can describe several. Use [Manual report-to-study linkage](study-linkage.md) before interpreting `included_studies`.
4. Attach the correct source, inspect its canonical blocks, and retain version labels and URLs. Every attachment becomes a new immutable version; source attachment alone does not alter eligibility or retrieval status. [Source documents and version handling](source-documents.md) explains identity checks, PDF limits and quotation locators.
5. Enter findings and appraisal judgments with exact quotations and context, then have an independent reviewer verify the current revision. New source versions require new anchored revisions and checks. [Verified evidence](verified-evidence.md) provides the full runnable workflow. [Project passage retrieval](project-retrieval.md) returns candidates for review; a candidate is not a verified finding.
6. Inspect pending and unresolved states, current evidence and audit history before exporting. Reconciled arithmetic does not establish search coverage, completed screening, valid appraisal or a clinically justified synthesis. Use the research protocol and human judgment to establish those conclusions.
