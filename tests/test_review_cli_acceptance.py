"""Fresh-process, fresh-directory review workflow acceptance evidence."""

import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "review"


def run_cli(tmp_path, database, *arguments, success=True):
    environment = os.environ.copy()
    for key in list(environment):
        if any(provider in key.upper() for provider in ("AGNES", "OPENAI", "ANTHROPIC")):
            environment.pop(key)
    result = subprocess.run(
        [sys.executable, str(ROOT / "review.py"), "--db", str(database), *map(str, arguments)],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30,
    )
    if success:
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
        return json.loads(result.stdout)
    assert result.returncode != 0
    assert result.stderr.strip()
    assert "Traceback" not in result.stderr
    assert result.stdout.strip() == ""
    return result


def test_fresh_cli_records_provenance_screening_history_and_exports(tmp_path):
    database = tmp_path / "ledger" / "reviews.sqlite3"
    assert run_cli(tmp_path, database, "projects") == []
    created = run_cli(
        tmp_path, database, "create", "--title", "Monitoring scoping review", "--type", "scoping",
        "--question", "Which approaches improve postoperative monitoring?", "--protocol", "Protocol version 1",
        "--eligibility-json", '{"population":"Adults","designs":["trial","cohort"]}',
    )
    project_id = created["id"]
    assert created["review_type"] == "scoping"
    assert created["eligibility"] == {"population": "Adults", "designs": ["trial", "cohort"]}
    query = '("Postoperative Care"[MeSH Terms])\nAND "monitoring"[Title/Abstract]'
    searched_at = "2026-10-03T12:00:00+08:00"
    path = tmp_path / "export with spaces.json"
    path.write_bytes((FIXTURES / "medical_records.json").read_bytes())
    imported = run_cli(
        tmp_path, database, "import", project_id, path, "--source", "PubMed", "--query", query,
        "--searched-at", searched_at, "--filters-json", '{"language":["English"],"publication_year":{"from":2020}}',
        "--notes", "Export of first eight hits", "--reported-count", "42", "--import-key", "pubmed-001",
    )
    assert imported["identified"] == 8 and imported["new_records"] == 6 and imported["duplicates"] == 2
    history = run_cli(tmp_path, database, "history", project_id)
    assert len(history) == 1
    search = history[0]
    assert search["query"] == query
    assert search["searched_at"] == searched_at
    assert search["source"] == "PubMed"
    assert search["notes"] == "Export of first eight hits"
    assert search["filters"] == {"language": ["English"], "publication_year": {"from": 2020}}
    assert search["reported_count"] == 42
    assert search["source_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert Path(search["source_file"]).name == path.name
    records = run_cli(tmp_path, database, "records", project_id)
    assert len(records) == 6
    assert all(row["title_abstract_state"] == "pending" for row in records)
    record_id = next(row["id"] for row in records if row["pmid"] == "39001001")
    run_cli(tmp_path, database, "screen", project_id, record_id, "--stage", "title_abstract",
            "--decision", "include", "--reviewer", "Alice")
    run_cli(tmp_path, database, "screen", project_id, record_id, "--stage", "title_abstract",
            "--decision", "exclude", "--reviewer", "Bob", "--reason", "Outcome unclear")
    counts = run_cli(tmp_path, database, "counts", project_id)
    assert counts["records_screening_unresolved"] == 1 and counts["records_excluded"] == 0
    run_cli(tmp_path, database, "adjudicate", project_id, record_id, "--stage", "title_abstract",
            "--decision", "include", "--reviewer", "Coordinator", "--reason", "Protocol outcome present")
    run_cli(tmp_path, database, "fulltext", project_id, record_id, "--status", "requested", "--reviewer", "Librarian")
    run_cli(tmp_path, database, "fulltext", project_id, record_id, "--status", "retrieved", "--reviewer", "Librarian")
    run_cli(tmp_path, database, "screen", project_id, record_id, "--stage", "full_text",
            "--decision", "exclude", "--reviewer", "Alice", "--reason", 'Outcome absent, "confirmed"\nFull text checked')
    events = run_cli(tmp_path, database, "decisions", project_id)
    assert len(events["decisions"]) == 4
    assert len(events["retrieval_events"]) == 2
    counts = run_cli(tmp_path, database, "counts", project_id)
    assert counts["records_identified"] == 8 and counts["duplicate_records_removed"] == 2 and counts["unique_records"] == 6
    assert counts["records_awaiting_screening"] == 5
    assert counts["reports_excluded"] == 1 and counts["reports_included"] == 0
    assert counts["reports_assessment_unresolved"] == 0
    assert counts["included_studies"] is None and counts["study_linkage_available"] is False
    assert counts["all_checks_passed"] is True and all(counts["reconciliation"].values())
    directory = tmp_path / "exported ledger"
    exported = run_cli(tmp_path, database, "export", project_id, directory)
    assert exported["counts"] == counts
    bundle = json.loads((directory / "project.json").read_text(encoding="utf-8"))
    assert bundle["counts"] == counts
    assert bundle["search_runs"][0]["source_sha256"] == search["source_sha256"]
    assert bundle["search_runs"][0]["query"] == query
    assert len(bundle["occurrences"]) == 8
    with (directory / "decisions.csv").open(encoding="utf-8", newline="") as handle:
        decision_rows = list(csv.DictReader(handle))
    assert decision_rows[-1]["reason"] == 'Outcome absent, "confirmed"\nFull text checked'
    assert [row["id"] for row in run_cli(tmp_path, database, "projects")] == [project_id]


def test_cli_unknown_search_metadata_zero_result_run_and_repeat_key(tmp_path):
    database = tmp_path / "reviews.sqlite3"
    project_id = run_cli(tmp_path, database, "create", "--title", "Zero search", "--type", "systematic", "--question", "What exists?")["id"]
    path = tmp_path / "zero.json"
    path.write_text("[]", encoding="utf-8")
    first = run_cli(tmp_path, database, "import", project_id, path, "--source", "Local export", "--import-key", "zero")
    assert run_cli(tmp_path, database, "import", project_id, path, "--source", "Local export", "--import-key", "zero") == first
    runs = run_cli(tmp_path, database, "history", project_id)
    assert len(runs) == 1
    assert runs[0]["query"] is None and runs[0]["searched_at"] is None and runs[0]["reported_count"] is None
    assert runs[0]["source_sha256"] == hashlib.sha256(b"[]").hexdigest()
    counts = run_cli(tmp_path, database, "counts", project_id)
    assert counts["records_identified"] == counts["unique_records"] == 0
    assert counts["all_checks_passed"] is True
    path.write_text('[{"title":"Changed export"}]', encoding="utf-8")
    run_cli(tmp_path, database, "import", project_id, path, "--source", "Local export", "--import-key", "zero", success=False)
    assert run_cli(tmp_path, database, "history", project_id) == runs


@pytest.mark.parametrize("bad_arguments", [
    ("create", "--title", "", "--type", "systematic", "--question", "Question"),
    ("create", "--title", "Title", "--type", "systematic", "--question", "Question", "--eligibility-json", "{broken"),
    ("counts", "unknown-project"),
    ("export", "unknown-project", "outputs"),
    ("screen", "unknown-project", "unknown-record", "--stage", "title_abstract", "--decision", "include", "--reviewer", "Alice"),
])
def test_cli_errors_are_concise_json_stdout_remains_clean(tmp_path, bad_arguments):
    database = tmp_path / "reviews.sqlite3"
    run_cli(tmp_path, database, *bad_arguments, success=False)
    assert run_cli(tmp_path, database, "projects") == []


def test_cli_invalid_import_and_missing_reason_preserve_prior_ledger(tmp_path):
    database = tmp_path / "reviews.sqlite3"
    project_id = run_cli(tmp_path, database, "create", "--title", "Validation", "--type", "scoping", "--question", "Question")["id"]
    path = tmp_path / "records.json"
    path.write_text('[{"title":"Good"},{"title":"Bad DOI","doi":"broken"}]', encoding="utf-8")
    run_cli(tmp_path, database, "import", project_id, path, "--source", "PubMed", success=False)
    assert run_cli(tmp_path, database, "history", project_id) == []
    assert run_cli(tmp_path, database, "records", project_id) == []
    path.write_text('[{"title":"Good","doi":"10.5555/good"}]', encoding="utf-8")
    run_cli(tmp_path, database, "import", project_id, path, "--source", "PubMed")
    record_id = run_cli(tmp_path, database, "records", project_id)[0]["id"]
    run_cli(tmp_path, database, "screen", project_id, record_id, "--stage", "title_abstract",
            "--decision", "exclude", "--reviewer", "Alice", success=False)
    events = run_cli(tmp_path, database, "decisions", project_id)
    assert events["decisions"] == [] and events["retrieval_events"] == []
    run_cli(tmp_path, database, "screen", project_id, record_id, "--stage", "title_abstract",
            "--decision", "include", "--reviewer", "Alice")
    before = run_cli(tmp_path, database, "decisions", project_id)
    run_cli(tmp_path, database, "fulltext", project_id, record_id, "--status", "not_retrieved", "--reviewer", "Librarian", success=False)
    assert run_cli(tmp_path, database, "decisions", project_id) == before
    run_cli(tmp_path, database, "import", project_id, path, "--source", "PubMed", "--filters-json", "[]", success=False)
    run_cli(tmp_path, database, "import", project_id, path, "--source", "PubMed", "--searched-at", "yesterday", success=False)
    assert len(run_cli(tmp_path, database, "history", project_id)) == 1
