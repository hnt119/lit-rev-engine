import hashlib
import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "review.py"


def invoke(tmp_path, *arguments, succeeds=True):
    result = subprocess.run([sys.executable, str(SCRIPT), "--db", str(tmp_path / "ledger.sqlite3"), *arguments], cwd=tmp_path, capture_output=True, text=True)
    assert (result.returncode == 0) is succeeds, result.stderr
    if succeeds:
        assert result.stderr == ""
        return json.loads(result.stdout)
    assert result.stdout == ""
    assert "Traceback" not in result.stderr
    return result.stderr


def test_noninteractive_cli_workflow_with_checksum_and_idempotency(tmp_path):
    project = invoke(tmp_path, "create", "--title", "Trial review", "--type", "systematic", "--question", "Benefits?", "--eligibility-json", '{"population":"adults"}')
    source = tmp_path / "records.json"
    source.write_text(json.dumps([{"title": "A trial", "doi": "10.1234/a", "authors": ["Smith, Anne"], "year": 2024, "additional": "raw detail"}]))
    args = ["import", project["id"], str(source), "--source", "PubMed", "--query", "adult trial", "--searched-at", "2026-10-03T09:00:00+08:00", "--filters-json", '{"language":"English"}', "--reported-count", "12", "--import-key", "once"]
    imported = invoke(tmp_path, *args)
    assert invoke(tmp_path, *args) == imported
    history = invoke(tmp_path, "history", project["id"])
    assert len(history) == 1
    assert history[0]["source_file"] == str(source)
    assert history[0]["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert history[0]["reported_count"] == 12
    assert history[0]["searched_at"] == "2026-10-03T09:00:00+08:00"
    record_id = invoke(tmp_path, "records", project["id"])[0]["id"]
    invoke(tmp_path, "screen", project["id"], record_id, "--stage", "title_abstract", "--decision", "include", "--reviewer", "Alice")
    invoke(tmp_path, "fulltext", project["id"], record_id, "--status", "retrieved", "--reviewer", "Librarian")
    invoke(tmp_path, "screen", project["id"], record_id, "--stage", "full_text", "--decision", "include", "--reviewer", "Alice")
    counts = invoke(tmp_path, "counts", project["id"])
    assert counts["reports_included"] == 1
    assert counts["included_studies"] is None
    assert counts["all_checks_passed"]
    histories = invoke(tmp_path, "decisions", project["id"])
    assert len(histories["decisions"]) == 2
    assert len(histories["retrieval_events"]) == 1
    exported = invoke(tmp_path, "export", project["id"], str(tmp_path / "output"))
    assert exported["counts"] == counts
    assert invoke(tmp_path, "projects") == [project]


def test_cli_errors_do_not_print_tracebacks_or_create_records(tmp_path):
    project = invoke(tmp_path, "create", "--title", "Trial review", "--type", "scoping", "--question", "Question")
    source = tmp_path / "empty.json"
    source.write_text("[]")
    invalid_filters = invoke(tmp_path, "import", project["id"], str(source), "--source", "PubMed", "--filters-json", "[]", succeeds=False)
    assert "JSON object" in invalid_filters
    invalid_date = invoke(tmp_path, "import", project["id"], str(source), "--source", "PubMed", "--searched-at", "yesterday", succeeds=False)
    assert "ISO" in invalid_date
    unknown = invoke(tmp_path, "counts", "unknown", succeeds=False)
    assert "Unknown project" in unknown
    assert invoke(tmp_path, "history", project["id"]) == []
    assert invoke(tmp_path, "records", project["id"]) == []
    malformed = invoke(tmp_path, "create", "--title", "Bad", "--type", "systematic", "--question", "Question", "--eligibility-json", "not json", succeeds=False)
    assert "Invalid eligibility JSON" in malformed
